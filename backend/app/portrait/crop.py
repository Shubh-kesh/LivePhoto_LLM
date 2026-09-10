"""Passport-style portrait crop (M5.7 §32-36, §59; corrected framing).

Deterministic and versioned (``passport-crop-v3``). The crop intentionally preserves:

- a top margin above the highest visible hair region (hair is never clipped),
- visible left/right margins beside the shoulders,
- upper shoulders (neck + shoulder line),
- a consistent 3:4 portrait aspect without stretching.

The subject anchor combines the matte (foreground) bounds with the M3 primary face box so the
crop is not just the face rectangle: shoulders and hair silhouette drive the frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CROP_VERSION = "passport-crop-v3"
PORTRAIT_ASPECT = 3 / 4  # width / height

#: Head + hair occupy roughly 50-55% of the output height (was ~60% in v1, too tight).
HEAD_HEIGHT_RATIO = 0.52
#: Top margin above the highest visible hair, as a fraction of output height.
TOP_MARGIN_RATIO = 0.10
#: Hair pad strictly above the matte's top foreground pixel (belt-and-braces for hair clipping).
HAIR_PAD_RATIO = 0.02
#: Shoulders occupy ~84% of the output width => ~8% lateral breathing room on each side.
SHOULDER_WIDTH_RATIO = 0.84
#: Bottom margin below the shoulder line.
BOTTOM_MARGIN_RATIO = 0.04

ALPHA_THRESHOLD = 0.5


@dataclass(frozen=True)
class CropBox:
    x0: int
    y0: int
    x1: int
    y1: int
    width: int
    height: int
    normalized: tuple[float, float, float, float]

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0


def _foreground_bbox(alpha: np.ndarray) -> tuple[int, int, int, int]:
    mask = alpha > ALPHA_THRESHOLD
    if not mask.any():
        raise ValueError("no foreground subject detected")
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    y0 = int(np.argmax(rows))
    y1 = int(len(rows) - np.argmax(rows[::-1]))
    x0 = int(np.argmax(cols))
    x1 = int(len(cols) - np.argmax(cols[::-1]))
    return x0, y0, x1, y1


def passport_crop(
    alpha: np.ndarray,
    image_size: tuple[int, int],
    face_box_normalized: tuple[float, float, float, float] | None = None,
) -> CropBox:
    """Compute a deterministic 3:4 passport-style crop (v3 framing).

    Pipeline: matte foreground bounds -> head + shoulder anchors -> top/side margins ->
    enforce 3:4 -> clamp to source.
    """
    width, height = image_size
    fg_x0, fg_y0, fg_x1, fg_y1 = _foreground_bbox(alpha)
    fg_width = max(1, fg_x1 - fg_x0)
    fg_height = max(1, fg_y1 - fg_y0)

    # --- Subject anchors -----------------------------------------------------
    if face_box_normalized is not None:
        fx, fy, fw, fh = face_box_normalized
        head_center_x = int((fx + fw / 2) * width)
        head_top = int(fy * height)
        head_bottom = int((fy + fh) * height)
    else:
        head_center_x = (fg_x0 + fg_x1) // 2
        head_top = fg_y0
        head_bottom = fg_y0 + int(fg_height * 0.42)
    head_extent = max(8, head_bottom - head_top)

    # --- Vertical: height driven by head sizing (~52% of output) -------------
    height_from_head = head_extent / HEAD_HEIGHT_RATIO

    # --- Horizontal: width driven by shoulder width + side margins -----------
    width_from_shoulders = fg_width / SHOULDER_WIDTH_RATIO

    # --- Combine into an exact 3:4 box --------------------------------------
    width_needed = max(int(0.75 * height_from_head), int(width_from_shoulders))
    crop_height = max(16, round(width_needed / PORTRAIT_ASPECT))
    crop_width = int(crop_height * PORTRAIT_ASPECT)

    # --- Fit: never larger than the source in EITHER dimension ----------------
    # A 3:4 frame must satisfy frame_width = 0.75 * frame_height. The largest such frame that fits
    # inside the source is bounded by BOTH width and height. Scale the desired frame down to that
    # limit so CropBox coordinates are always inside the source — fixes mobile portrait sources
    # where the desired 3:4 crop width exceeds the source width (e.g. 720x1280 with a desired width
    # of 1143 would otherwise yield a negative x0).
    if crop_width > width or crop_height > height:
        fit_height = height
        fit_width = int(fit_height * PORTRAIT_ASPECT)
        if fit_width > width:
            fit_width = width
            fit_height = round(fit_width / PORTRAIT_ASPECT)
        crop_width = max(12, min(crop_width, fit_width))
        crop_height = max(12, min(crop_height, fit_height))
    # Defensive invariants regardless of integer rounding:
    crop_width = min(crop_width, width)
    crop_height = min(crop_height, height)

    # --- Top margin: above the head AND strictly above the hair --------------
    hair_pad = max(2, int(HAIR_PAD_RATIO * crop_height))
    crop_top = head_top - int(TOP_MARGIN_RATIO * crop_height)
    # Guarantee the top boundary stays above the highest visible hair.
    crop_top = min(crop_top, fg_y0 - hair_pad)
    crop_top = max(0, crop_top)

    # --- Bottom: top-anchored so hair is never sacrificed; include shoulders when slack allows.
    # We only shift the frame downward by the available top slack; the top boundary NEVER drops
    # below the hair pad (hair preservation is a hard requirement).
    crop_bottom = crop_top + crop_height
    bottom_margin = max(2, int(BOTTOM_MARGIN_RATIO * crop_height))
    needed_bottom = fg_y1 + bottom_margin
    if crop_bottom < needed_bottom:
        max_shift = max(0, (fg_y0 - hair_pad) - crop_top)
        shift = min(needed_bottom - crop_bottom, max_shift)
        crop_top += shift
        crop_bottom += shift

    # --- Horizontal: face-centered placement with balanced shoulder framing -----
    # Weight the crop center strongly toward the primary face midline; the matte center is a
    # secondary guide so asymmetric hair/clothing never drags the portrait off-center (M5.7 fix).
    matte_center_x = (fg_x0 + fg_x1) // 2
    face_weight = 0.7
    face_center_x = head_center_x
    desired_center_x = round(face_weight * face_center_x + (1 - face_weight) * matte_center_x)

    # Both shoulders must keep a visible minimum side margin (target ~8%, floor ~4%).
    min_side = max(2, int(0.04 * crop_width))

    # Feasible left edge that keeps both shoulder margins >= min_side.
    lo = fg_x1 + min_side - crop_width
    hi = fg_x0 - min_side
    if lo <= hi:
        # Prefer the face-centered placement, clamped into the feasible range so both shoulders
        # stay visible with their minimum margin.
        crop_x0 = max(lo, min(hi, desired_center_x - crop_width // 2))
    else:
        # Source cannot hold both minimum margins: keep face-centered, then clamp to the image.
        crop_x0 = desired_center_x - crop_width // 2
    crop_x0 = max(0, crop_x0)
    if crop_x0 + crop_width > width:
        crop_x0 = width - crop_width
    crop_x1 = crop_x0 + crop_width

    # --- Clamp to source while preserving 3:4 --------------------------------
    if crop_x0 < 0:
        crop_x0, crop_x1 = 0, crop_width
    if crop_x1 > width:
        crop_x1, crop_x0 = width, width - crop_width
    if crop_bottom > height:
        crop_bottom = height
        crop_top = max(0, crop_bottom - crop_height)
    if crop_top < 0:
        crop_top = 0
        crop_bottom = min(crop_top + crop_height, height)

    crop_width = crop_x1 - crop_x0
    crop_height = crop_bottom - crop_top

    return CropBox(
        x0=crop_x0,
        y0=crop_top,
        x1=crop_x1,
        y1=crop_bottom,
        width=crop_width,
        height=crop_height,
        normalized=(
            round(crop_x0 / width, 4),
            round(crop_top / height, 4),
            round(crop_x1 / width, 4),
            round(crop_bottom / height, 4),
        ),
    )
