"""Matte refinement tests (M5.7 correction §40)."""

from __future__ import annotations

import numpy as np

from app.portrait.matte import MATTE_REFINEMENT_VERSION, refine_matte


def _dark_on_dark_alpha(height: int = 800, width: int = 640) -> np.ndarray:
    """Synthetic matte: solid torso with mid alpha on a dark background + a disconnected blob."""
    alpha = np.zeros((height, width), dtype=np.float32)
    # Primary person: head (soft top), torso with mid alpha (dark shirt on dark bg).
    yy, xx = np.mgrid[0:height, 0:width]
    head = ((xx - 320) / 95) ** 2 + ((yy - 260) / 120) ** 2 <= 1.0
    shoulders = ((xx - 320) / 150) ** 2 + ((yy - 420) / 260) ** 2 <= 1.0
    alpha[head] = 0.92  # head confident
    alpha[shoulders & ~head] = 0.45  # torso mid alpha -> should be reinforced to opaque
    # Soft hair band above the head (kept soft).
    hair_band = ((xx - 320) / 100) ** 2 + ((yy - 190) / 60) ** 2 <= 1.0
    alpha[hair_band & ~head] = 0.6
    # Disconnected background blob (e.g. furniture/another person) with high alpha.
    blob = ((xx - 60) / 40) ** 2 + ((yy - 120) / 50) ** 2 <= 1.0
    alpha[blob] = 0.85
    return alpha


def test_body_interior_becomes_opaque() -> None:
    alpha = _dark_on_dark_alpha()
    out = refine_matte(alpha, face_box_normalized=(0.39, 0.26, 0.22, 0.24))
    # A mid-alpha torso pixel (below the forehead) is reinforced to near-opaque.
    y, x = 520, 320
    assert alpha[y, x] < 0.6
    assert out[y, x] >= 0.9


def test_far_background_remains_transparent() -> None:
    alpha = _dark_on_dark_alpha()
    out = refine_matte(alpha)
    assert out[10, 10] == 0.0
    assert out[700, 600] == 0.0


def test_soft_hair_alpha_is_preserved() -> None:
    alpha = _dark_on_dark_alpha()
    out = refine_matte(alpha, face_box_normalized=(0.39, 0.26, 0.22, 0.24))
    # A hair-band pixel above the forehead keeps its original soft alpha (not forced to 1).
    y, x = 180, 320
    assert alpha[y, x] < 1.0
    assert out[y, x] == alpha[y, x]


def test_unrelated_region_removed() -> None:
    alpha = _dark_on_dark_alpha()
    out = refine_matte(alpha, face_box_normalized=(0.39, 0.26, 0.22, 0.24))
    # The disconnected background blob is removed entirely.
    blob_pixel = (120, 60)
    assert alpha[blob_pixel] > 0.8
    assert out[blob_pixel] == 0.0


def test_primary_connected_region_retained() -> None:
    alpha = _dark_on_dark_alpha()
    out = refine_matte(alpha, face_box_normalized=(0.39, 0.26, 0.22, 0.24))
    # The primary person (head + torso) is retained.
    assert out[260, 320] > 0.8
    assert out[520, 320] >= 0.9


def test_no_face_anchor_falls_back_to_centroid() -> None:
    alpha = _dark_on_dark_alpha()
    out = refine_matte(alpha)
    # Without a face box the primary (largest central) component is retained via the centroid seed.
    assert out[260, 320] > 0.8
    assert out[120, 60] == 0.0


def test_version_constant() -> None:
    assert MATTE_REFINEMENT_VERSION == "matte-refinement-v3"
