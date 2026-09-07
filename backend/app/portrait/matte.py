"""Region-aware matte refinement (M5.7 correction).

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
"""

from __future__ import annotations

from collections import deque

import numpy as np

MATTE_REFINEMENT_VERSION = "matte-refinement-v2"

#: Confidence zones (provisional in-code thresholds).
SUPPORT_THRESHOLD = 0.35  # primary-person component seed mask (includes mid-alpha torso)
REMOVE_HIGH_BACKGROUND_THRESHOLD = 0.6  # disconnect-removal applies only to confident foreground
BODY_REINFORCE_THRESHOLD = 0.35  # mid alpha inside the body is raised to solid
BODY_REINFORCE_ALPHA = 0.95


def _connected_component(mask: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
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


def refine_matte(
    alpha: np.ndarray,
    face_box_normalized: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """Region-aware refinement: body reinforced, hair soft, disconnected regions removed."""
    alpha = np.asarray(alpha, dtype=np.float32)
    mask = alpha > SUPPORT_THRESHOLD
    seed = _seed_point(mask, face_box_normalized)
    if seed is None or not mask[seed]:
        # Cannot anchor the primary person reliably: leave the matte untouched (never blank it).
        return alpha

    support = _connected_component(mask, seed)

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
