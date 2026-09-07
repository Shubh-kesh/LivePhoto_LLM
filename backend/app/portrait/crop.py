"""Passport-style portrait crop (M5.7 §32-36, §59).

Deterministic and versioned (``passport-crop-v1``). The crop keeps head + hair (with top margin so
hair is never clipped), neck and upper shoulders, at a consistent 3:4 aspect ratio without
stretching the subject. The M3 primary face anchor (normalized box) is used when available so the
capture's primary face governs the crop rather than a background component (M5.7 §59).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CROP_VERSION = "passport-crop-v1"
PORTRAIT_ASPECT = 3 / 4  # width / height

#: Head occupies ~60% of the crop height; ~10% top margin above the hairline.
HEAD_HEIGHT_RATIO = 0.60
TOP_MARGIN_RATIO = 0.10

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
    """Compute a deterministic 3:4 passport-style crop anchored on the head."""
    width, height = image_size
    fg_x0, fg_y0, fg_x1, fg_y1 = _foreground_bbox(alpha)

    if face_box_normalized is not None:
        # Anchor the horizontal head center on the capture's primary face.
        fx, fy, fw, fh = face_box_normalized
        head_center_x = int((fx + fw / 2) * width)
        head_top = int(fy * height)
        head_bottom = int((fy + fh) * height)
        head_extent = max(8, head_bottom - head_top)
    else:
        head_center_x = (fg_x0 + fg_x1) // 2
        # Head occupies roughly the upper portion of the foreground extent.
        fg_h = max(8, fg_y1 - fg_y0)
        head_top = fg_y0
        head_bottom = fg_y0 + int(fg_h * 0.42)
        head_extent = max(8, head_bottom - head_top)

    crop_height = max(16, int(head_extent / HEAD_HEIGHT_RATIO))
    crop_width = max(12, int(crop_height * PORTRAIT_ASPECT))
    crop_height = int(crop_width / PORTRAIT_ASPECT)  # keep exact 3:4

    crop_top = head_top - int(TOP_MARGIN_RATIO * crop_height)
    crop_bottom = crop_top + crop_height
    crop_x0 = head_center_x - crop_width // 2
    crop_x1 = crop_x0 + crop_width

    # Clamp horizontally (never stretch; just shift) then re-center.
    if crop_x0 < 0:
        crop_x0, crop_x1 = 0, crop_width
    if crop_x1 > width:
        crop_x1, crop_x0 = width, width - crop_width

    # Clamp vertically; if taller than the image, shrink to fit keeping top margin priority.
    if crop_bottom > height:
        crop_bottom = height
        crop_top = crop_bottom - crop_height
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
