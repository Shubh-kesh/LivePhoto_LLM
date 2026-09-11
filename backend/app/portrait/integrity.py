"""Primary-subject matte integrity validation (pre-M6 portrait-quality fix).

A confirmed real failure (TX LP-20260910T150524236Z-7B4136; 720x1280, harsh lighting) showed that
raw MODNet alpha can already be badly fragmented in the primary face/head region (face/head/left
side missing), and that connected-component refinement then deleted further legitimate subject
pixels. A technically successful encode therefore produced a visually corrupted portrait.

This module provides a DETERMINISTIC, interpretable structural check over the primary face/head
region so such mattes fail closed (retryable portrait-quality failure) instead of being promoted.

Design constraints:
- Geometry only; no aesthetics, no demographics, no PII. Uses the M3 primary face box (geometry
  guidance only — never an authorization input).
- Soft hair edges are expected and must NOT fail. The check targets catastrophic corruption:
  a missing half-face, a large hole through the face, most of one side of the head missing, or a
  primary component fragmented beyond safe use.
- Thresholds are PROVISIONAL, deterministic and covered by tests (see the portrait processing docs).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

MATTE_INTEGRITY_VERSION = "portrait-matte-integrity-v1"

#: Foreground decision threshold for the (soft) alpha matte. Strict enough that soft hair alpha is
#: not counted, lenient enough that anti-aliased face edges are.
FOREGROUND_THRESHOLD = 0.5

#: Expanded head ROI relative to the primary face box (fractions of face width/height).
HEAD_EXPAND_X = 0.30
HEAD_EXPAND_TOP = 0.45
HEAD_EXPAND_BOTTOM = 0.20

#: Provisional integrity thresholds (documented; deterministic; regression-tested).
MIN_FACE_RETENTION = 0.55
MIN_HEAD_RETENTION = 0.45
MIN_LEFT_RIGHT_BALANCE = 0.35
MIN_COMPONENT_FACE_OVERLAP = 0.55
#: No-face-box fallback: reject only a degenerate (near-empty) matte.
MIN_GLOBAL_FOREGROUND = 0.02

#: Face-box sanity (normalized 0..1). Reject clearly nonsensical tiny/oversized boxes.
MIN_FACE_BOX_DIM = 0.03
MAX_FACE_BOX_DIM = 1.0
_FACE_BOX_EPSILON = 1e-9

#: Refinement is rejected (or reverted to raw) if it drops retention/balance beyond these.
MAX_REFINEMENT_RETENTION_DROP = 0.15
MAX_REFINEMENT_BALANCE_DROP = 0.25


@dataclass(frozen=True)
class MatteIntegrity:
    """Interpretable structural metrics over the primary face/head region."""

    ok: bool
    reason: str | None
    has_face_box: bool
    face_retention: float
    head_retention: float
    left_retention: float
    right_retention: float
    balance: float
    component_face_overlap: float
    foreground_ratio: float


def _clip_roi(
    x0: float, y0: float, x1: float, y1: float, width: int, height: int
) -> tuple[int, int, int, int]:
    ix0 = max(0, min(width, round(x0)))
    iy0 = max(0, min(height, round(y0)))
    ix1 = max(ix0, min(width, round(x1)))
    iy1 = max(iy0, min(height, round(y1)))
    return ix0, iy0, ix1, iy1


def face_roi_px(
    face_box_normalized: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    fx, fy, fw, fh = face_box_normalized
    return _clip_roi(fx * width, fy * height, (fx + fw) * width, (fy + fh) * height, width, height)


def head_roi_px(
    face_box_normalized: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    fx, fy, fw, fh = face_box_normalized
    return _clip_roi(
        (fx - HEAD_EXPAND_X * fw) * width,
        (fy - HEAD_EXPAND_TOP * fh) * height,
        (fx + fw + HEAD_EXPAND_X * fw) * width,
        (fy + fh + HEAD_EXPAND_BOTTOM * fh) * height,
        width,
        height,
    )


def _retention(foreground: np.ndarray, roi: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = roi
    region = foreground[y0:y1, x0:x1]
    if region.size == 0:
        return 0.0
    return float(np.count_nonzero(region)) / float(region.size)


def _balance(left: float, right: float) -> float:
    high = max(left, right)
    if high <= 0.0:
        return 0.0
    return min(left, right) / high


def _pick_seed(foreground: np.ndarray, roi: tuple[int, int, int, int]) -> tuple[int, int] | None:
    """Prefer the face-box center; otherwise the strongest foreground pixel inside the ROI."""
    x0, y0, x1, y1 = roi
    if x1 <= x0 or y1 <= y0:
        return None
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    if foreground[cy, cx]:
        return (cy, cx)
    region = foreground[y0:y1, x0:x1]
    if not region.any():
        return None
    ys, xs = np.nonzero(region)
    # First foreground pixel in row-major order (deterministic).
    return (int(ys[0] + y0), int(xs[0] + x0))


def component_face_overlap(
    foreground: np.ndarray, face_box_normalized: tuple[float, float, float, float]
) -> float:
    """Fraction of the primary face ROI covered by the primary connected foreground component."""
    height, width = foreground.shape
    roi = face_roi_px(face_box_normalized, width, height)
    x0, y0, x1, y1 = roi
    if x1 <= x0 or y1 <= y0:
        return 0.0
    seed = _pick_seed(foreground, roi)
    if seed is None:
        return 0.0
    # Imported lazily to avoid a circular import at module load.
    from app.portrait.matte import connected_component_mask

    component = connected_component_mask(foreground, seed)
    region = component[y0:y1, x0:x1]
    return float(np.count_nonzero(region)) / float(region.size)


def validate_portrait_matte(
    alpha: np.ndarray,
    face_box_normalized: tuple[float, float, float, float] | None = None,
    *,
    min_face_retention: float = MIN_FACE_RETENTION,
    min_head_retention: float = MIN_HEAD_RETENTION,
    min_balance: float = MIN_LEFT_RIGHT_BALANCE,
    min_component_overlap: float = MIN_COMPONENT_FACE_OVERLAP,
) -> MatteIntegrity:
    """Deterministic structural integrity of a (raw or refined) alpha matte.

    With a face box: requires acceptable face retention, head retention, left/right balance and
    primary-component coverage of the face ROI. Without a face box: only rejects a degenerate
    (near-empty) matte — the strong gate needs the geometry guidance.
    """
    alpha = np.asarray(alpha, dtype=np.float32)
    height, width = alpha.shape
    foreground = alpha >= FOREGROUND_THRESHOLD
    foreground_ratio = float(np.count_nonzero(foreground)) / float(alpha.size or 1)

    if face_box_normalized is None:
        ok = foreground_ratio >= MIN_GLOBAL_FOREGROUND
        return MatteIntegrity(
            ok=ok,
            reason=None if ok else "empty_matte",
            has_face_box=False,
            face_retention=0.0,
            head_retention=0.0,
            left_retention=0.0,
            right_retention=0.0,
            balance=0.0,
            component_face_overlap=0.0,
            foreground_ratio=foreground_ratio,
        )

    face_roi = face_roi_px(face_box_normalized, width, height)
    head_roi = head_roi_px(face_box_normalized, width, height)

    face_retention = _retention(foreground, face_roi)
    head_retention = _retention(foreground, head_roi)
    x0, y0, x1, y1 = face_roi
    mid_x = (x0 + x1) // 2
    left_retention = _retention(foreground, (x0, y0, mid_x, y1))
    right_retention = _retention(foreground, (mid_x, y0, x1, y1))
    balance = _balance(left_retention, right_retention)
    overlap = component_face_overlap(foreground, face_box_normalized)

    reason: str | None = None
    if face_retention < min_face_retention:
        reason = "face_retention_low"
    elif overlap < min_component_overlap:
        reason = "face_component_fragmented"
    elif head_retention < min_head_retention:
        reason = "head_retention_low"
    elif balance < min_balance:
        reason = "face_asymmetry"

    return MatteIntegrity(
        ok=reason is None,
        reason=reason,
        has_face_box=True,
        face_retention=face_retention,
        head_retention=head_retention,
        left_retention=left_retention,
        right_retention=right_retention,
        balance=balance,
        component_face_overlap=overlap,
        foreground_ratio=foreground_ratio,
    )


def refinement_is_acceptable(raw: MatteIntegrity, refined: MatteIntegrity) -> bool:
    """True only when refinement did not materially damage the primary face/head region.

    Requires the refined matte to still pass, and not to drop face retention or left/right balance
    beyond the documented tolerances relative to the raw matte.
    """
    return (
        refined.ok
        and refined.face_retention >= raw.face_retention - MAX_REFINEMENT_RETENTION_DROP
        and refined.balance >= raw.balance - MAX_REFINEMENT_BALANCE_DROP
    )


def _validated_face_box(
    values: Sequence[object],
) -> tuple[float, float, float, float] | None:
    """Validate four normalized face-box values; None when missing/nonsensical/out of range."""
    if len(values) != 4:
        return None
    nums: list[float] = []
    for value in values:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        nums.append(number)
    x, y, w, h = nums
    if x < 0.0 or y < 0.0 or w <= 0.0 or h <= 0.0:
        return None
    if x + w > 1.0 + _FACE_BOX_EPSILON or y + h > 1.0 + _FACE_BOX_EPSILON:
        return None
    if w < MIN_FACE_BOX_DIM or h < MIN_FACE_BOX_DIM:
        return None
    if w > MAX_FACE_BOX_DIM or h > MAX_FACE_BOX_DIM:
        return None
    return (x, y, w, h)


def validate_face_box_values(
    values: Sequence[object] | None,
) -> tuple[float, float, float, float] | None:
    """Validate an already-parsed (e.g. persisted capture-metadata) face box."""
    if values is None:
        return None
    return _validated_face_box(values)


def parse_normalized_face_box(
    value: str | None,
) -> tuple[float, float, float, float] | None:
    """Parse and STRICTLY validate ``"x,y,w,h"`` normalized face-box form data.

    Rejects empty/malformed values, non-finite numbers, negatives, non-positive width/height,
    boxes extending past the frame (``x+w > 1`` / ``y+h > 1``), and clearly nonsensical tiny or
    oversized boxes. Geometry guidance only — never an authorization input.
    """
    if not value or not value.strip():
        return None
    parts = value.split(",")
    if len(parts) != 4:
        return None
    try:
        nums: list[float] = [float(p) for p in parts]
    except ValueError:
        return None
    return _validated_face_box(nums)
