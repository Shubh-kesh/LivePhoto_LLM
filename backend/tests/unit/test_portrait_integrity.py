"""Primary-subject matte integrity tests (pre-M6 portrait-quality fix).

Synthetic mattes reproduce the important geometries from the confirmed failure
(face/head fragmentation, one side separated, destructive cleanup would erase valid face pixels).
"""

from __future__ import annotations

import numpy as np

from app.portrait.integrity import (
    component_face_overlap,
    parse_normalized_face_box,
    refinement_is_acceptable,
    validate_portrait_matte,
)
from app.portrait.matte import refine_matte

W = 720
H = 1280
FACE = (0.30, 0.20, 0.40, 0.22)  # normalized primary face box


def _healthy(width: int = W, height: int = H, face=FACE) -> np.ndarray:
    alpha = np.zeros((height, width), dtype=np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    fx, fy, fw, fh = face
    cx, cy = (fx + fw / 2) * width, (fy + fh / 2) * height
    rx, ry = fw * width * 0.58, fh * height * 0.62
    head = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
    torso = (yy > (fy + fh) * height) & (np.abs(xx - cx) < fw * width * 0.95)
    alpha[head | torso] = 0.95
    return alpha


def _face_px(face=FACE, width=W, height=H):
    fx, fy, fw, fh = face
    return (
        int(fx * width),
        int(fy * height),
        int((fx + fw) * width),
        int((fy + fh) * height),
    )


def test_healthy_matte_passes_integrity() -> None:
    result = validate_portrait_matte(_healthy(), FACE)
    assert result.ok, result.reason
    assert result.face_retention > 0.9
    assert result.balance > 0.8
    assert result.component_face_overlap > 0.9


def test_soft_hair_edges_alone_do_not_fail() -> None:
    alpha = _healthy()
    # Add a broad soft-alpha hair ring (well below the foreground threshold).
    yy, xx = np.mgrid[0:H, 0:W]
    fx, fy, fw, fh = FACE
    cx, cy = (fx + fw / 2) * W, (fy + fh / 2) * H
    ring = ((xx - cx) / (fw * W * 0.75)) ** 2 + ((yy - cy) / (fh * H * 0.80)) ** 2 <= 1.0
    alpha[ring & (alpha < 0.5)] = 0.3
    result = validate_portrait_matte(alpha, FACE)
    assert result.ok, result.reason


def test_catastrophic_central_face_hole_fails() -> None:
    alpha = _healthy()
    x0, y0, x1, y1 = _face_px()
    cx = (x0 + x1) // 2
    # Large vertical hole through the face/head (60% width, 80% height of the face).
    hx0 = cx - int(0.30 * (x1 - x0))
    hx1 = cx + int(0.30 * (x1 - x0))
    hy0 = y0 + int(0.10 * (y1 - y0))
    hy1 = y0 + int(0.90 * (y1 - y0))
    alpha[hy0:hy1, hx0:hx1] = 0.0
    result = validate_portrait_matte(alpha, FACE)
    assert not result.ok
    assert result.reason in {"face_retention_low", "face_component_fragmented"}


def test_half_face_missing_fails() -> None:
    alpha = _healthy()
    x0, y0, x1, y1 = _face_px()
    mid = (x0 + x1) // 2
    alpha[y0:y1, x0:mid] = 0.0  # left half of the face gone
    result = validate_portrait_matte(alpha, FACE)
    assert not result.ok
    assert result.balance < 0.35


def test_severe_left_right_asymmetry_fails() -> None:
    alpha = _healthy()
    x0, y0, x1, y1 = _face_px()
    mid = (x0 + x1) // 2
    # Left half of the face keeps only every 4th row (sparse); the right half stays solid.
    alpha[y0:y1, x0:mid] = 0.0
    alpha[y0:y1:4, x0:mid] = 0.95
    result = validate_portrait_matte(alpha, FACE)
    assert not result.ok
    assert result.balance < 0.35


def test_fragmented_primary_component_fails() -> None:
    alpha = np.zeros((H, W), dtype=np.float32)
    x0, y0, x1, y1 = _face_px()
    width = x1 - x0
    # Two disconnected columns inside the face ROI; the seed (face center) sits in the right one.
    alpha[y0:y1, x0 : x0 + int(0.40 * width)] = 0.95
    alpha[y0:y1, x0 + int(0.45 * width) : x0 + int(0.90 * width)] = 0.95
    result = validate_portrait_matte(alpha, FACE)
    assert not result.ok
    assert result.reason == "face_component_fragmented"
    assert component_face_overlap(alpha >= 0.5, FACE) < 0.55


def test_component_guard_preserves_fragmented_subject_in_refinement() -> None:
    alpha = np.zeros((H, W), dtype=np.float32)
    x0, y0, x1, y1 = _face_px()
    width = x1 - x0
    # Left region (valid face) is disconnected from the selected primary component (right region).
    alpha[y0:y1, x0 : x0 + int(0.40 * width)] = 0.95
    alpha[y0:y1, x0 + int(0.45 * width) : x0 + int(0.90 * width)] = 0.95
    out = refine_matte(alpha, face_box_normalized=FACE)
    # Destructive cleanup must be skipped: the disconnected valid region is preserved (== raw).
    assert np.array_equal(out, alpha)


def test_small_disconnected_background_person_still_removed() -> None:
    alpha = _healthy()
    # A small high-alpha background blob far from the face (e.g. another person).
    alpha[30:90, 30:90] = 0.9
    raw = validate_portrait_matte(alpha, FACE)
    assert raw.ok
    out = refine_matte(alpha, face_box_normalized=FACE)
    assert out[60, 60] == 0.0  # background blob removed
    refined = validate_portrait_matte(out, FACE)
    assert refined.ok
    assert refinement_is_acceptable(raw, refined)


def test_refinement_acceptable_rejects_material_damage() -> None:
    raw = validate_portrait_matte(_healthy(), FACE)
    damaged = _healthy()
    x0, y0, x1, y1 = _face_px()
    mid = (x0 + x1) // 2
    damaged[y0:y1, x0:mid] = 0.0  # refinement erased half the face
    refined = validate_portrait_matte(damaged, FACE)
    assert not refinement_is_acceptable(raw, refined)


def test_no_face_box_only_rejects_empty_matte() -> None:
    assert validate_portrait_matte(_healthy()).ok
    assert not validate_portrait_matte(np.zeros((H, W), dtype=np.float32)).ok


def test_parse_normalized_face_box() -> None:
    assert parse_normalized_face_box("0.1,0.2,0.3,0.4") == (0.1, 0.2, 0.3, 0.4)
    assert parse_normalized_face_box("") is None
    assert parse_normalized_face_box("1,2,3") is None
    assert parse_normalized_face_box("a,b,c,d") is None
    assert parse_normalized_face_box("0.5,0.5,0,0.2") is None  # zero width
    # Out-of-range / overflowing boxes are REJECTED (not clamped).
    assert parse_normalized_face_box("1.5,-0.5,0.4,0.4") is None
    assert parse_normalized_face_box("0.8,0.2,0.4,0.4") is None  # x + w > 1
    assert parse_normalized_face_box("0.2,0.8,0.4,0.4") is None  # y + h > 1
    # Nonsensical tiny / non-finite boxes are rejected.
    assert parse_normalized_face_box("0.5,0.5,0.01,0.4") is None
    assert parse_normalized_face_box("0.5,0.5,0.4,0.01") is None
    assert parse_normalized_face_box("nan,0.2,0.3,0.4") is None
    assert parse_normalized_face_box("inf,0.2,0.3,0.4") is None
