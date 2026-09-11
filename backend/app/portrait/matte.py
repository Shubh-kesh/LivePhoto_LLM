"""Region-aware matte refinement (M5.7 correction; pre-M6 integrity guard).

MODNet produces a soft alpha matte that is desirable around hair and fine contours but undesirable
in the interior of solid clothing/torso where similar-luminance backgrounds can cause soft "tear"
artifacts. This deterministic post-processing distinguishes:

- fine-edge foreground (hair, hairline, ears, soft contours) -> keep the original soft alpha,
- solid body foreground (face, neck, torso, shoulders) -> reinforce high-confidence foreground so
  dark clothing on dark backgrounds stays opaque,
- far background -> force transparent,
- disconnected background people/objects -> removed (only the primary-person component is kept).

It is numpy-only (no OpenCV/SciPy). The primary-person component is anchored to the M3 primary face
box so foreground is never chosen by largest-component alone.

PRE-M6 GUARD: connected-component cleanup can delete legitimate parts of a fragmented primary
subject. Before any destructive removal, the selected primary component must credibly cover the
known primary face region; otherwise this function preserves the raw matte untouched (removing
uncertain parts of the primary subject is worse than leaving background). Raw-matte integrity is
still enforced separately by ``app.portrait.integrity`` — this guard never authorizes a broken
matte.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from app.portrait.integrity import MIN_COMPONENT_FACE_OVERLAP, face_roi_px

MATTE_REFINEMENT_VERSION = "matte-refinement-v3"

#: Confidence zones (provisional in-code thresholds).
SUPPORT_THRESHOLD = 0.35  # primary-person component seed mask (includes mid-alpha torso)
REMOVE_HIGH_BACKGROUND_THRESHOLD = 0.6  # disconnect-removal applies only to confident foreground
BODY_REINFORCE_THRESHOLD = 0.35  # mid alpha inside the body is raised to solid
BODY_REINFORCE_ALPHA = 0.95


def connected_component_mask(mask: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    """4-connected component of ``mask`` containing ``seed`` (deterministic, numpy-only)."""
    component = np.zeros_like(mask, dtype=bool)
    height, width = mask.shape
    sy, sx = seed
    if not (0 <= sy < height and 0 <= sx < width) or not mask[sy, sx]:
        return component
    stack = deque([(sy, sx)])
    component[sy, sx] = True
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not component[ny, nx]:
                component[ny, nx] = True
                stack.append((ny, nx))
    return component


def _seed_point(
    mask: np.ndarray,
    face_box_normalized: tuple[float, float, float, float] | None,
) -> tuple[int, int] | None:
    height, width = mask.shape
    if face_box_normalized is not None:
        fx, fy, fw, fh = face_box_normalized
        return (int((fy + fh / 2) * height), int((fx + fw / 2) * width))
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return None
    ys = np.where(rows)[0]
    xs = np.where(cols)[0]
    return (int((ys[0] + ys[-1]) // 2), int((xs[0] + xs[-1]) // 2))


def _component_covers_face(
    support: np.ndarray, face_box_normalized: tuple[float, float, float, float]
) -> bool:
    """True when the primary component credibly covers the primary face ROI.

    When false, destructive disconnected-component removal is skipped so valid parts of a
    fragmented primary subject are never erased.
    """
    height, width = support.shape
    x0, y0, x1, y1 = face_roi_px(face_box_normalized, width, height)
    if x1 <= x0 or y1 <= y0:
        return True  # cannot assess the ROI -> do not block on unknown geometry
    region = support[y0:y1, x0:x1]
    coverage = float(np.count_nonzero(region)) / float(region.size)
    return coverage >= MIN_COMPONENT_FACE_OVERLAP


def refine_matte(
    alpha: np.ndarray,
    face_box_normalized: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """Region-aware refinement: body reinforced, hair soft, disconnected regions removed.

    Destructive cleanup is skipped (raw matte preserved) when a face box is supplied but the
    selected primary component does not credibly cover the primary face region.
    """
    alpha = np.asarray(alpha, dtype=np.float32)
    mask = alpha > SUPPORT_THRESHOLD
    seed = _seed_point(mask, face_box_normalized)
    if seed is None or not mask[seed]:
        # Cannot anchor the primary person reliably: leave the matte untouched (never blank it).
        return alpha

    support = connected_component_mask(mask, seed)

    if face_box_normalized is not None and not _component_covers_face(support, face_box_normalized):
        # Untrustworthy primary component: preserve the raw matte rather than deleting uncertain
        # parts of the primary subject. (Raw integrity is enforced upstream.)
        return alpha

    # Remove confident foreground that is NOT part of the primary person (disconnected background
    # people, furniture, screens). Low/mid alpha (soft hair, uncertain edges) is left intact.
    out = np.where((alpha > REMOVE_HIGH_BACKGROUND_THRESHOLD) & ~support, 0.0, alpha)

    # Solid body/face reinforcement (neck, torso, shoulders, face) inside the primary support:
    # mid alpha is pushed to solid so dark clothing cannot tear into white.
    height = alpha.shape[0]
    if face_box_normalized is not None:
        face_top = int(face_box_normalized[1] * height)
    else:
        face_top = int(np.argmax(np.any(support, axis=1)))
    body_zone = np.zeros_like(support)
    body_zone[face_top:, :] = True
    reinforce = body_zone & support & (out >= BODY_REINFORCE_THRESHOLD)
    out = np.where(reinforce, np.maximum(out, BODY_REINFORCE_ALPHA), out)

    return out.astype(np.float32)
