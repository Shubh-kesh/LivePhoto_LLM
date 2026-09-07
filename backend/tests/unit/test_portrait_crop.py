"""Portrait crop framing tests (M5.7 correction §18)."""

from __future__ import annotations

import numpy as np

from app.portrait.crop import CROP_VERSION, PORTRAIT_ASPECT, passport_crop


def _synthetic_alpha(width: int = 640, height: int = 800) -> np.ndarray:
    """Head ellipse + shoulder trapezoid silhouette (deterministic fixture)."""
    yy, xx = np.mgrid[0:height, 0:width]
    # Head (hair included) ellipse.
    head = ((xx - 320) / 95) ** 2 + ((yy - 260) / 120) ** 2 <= 1.0
    # Shoulders: symmetric trapezoid widening downward (realistic portrait width), ending above the
    # frame bottom so a passport-style composition can include the shoulder line.
    half_width = np.maximum(110.0 + 0.15 * (yy - 340), 40.0)
    shoulders = (yy >= 340) & (yy <= 640) & (np.abs(xx - 320) <= half_width)
    alpha = (head | shoulders).astype(np.float32)
    return alpha


def _face_box() -> tuple[float, float, float, float]:
    # Face sits in the upper part of the head.
    return (0.39, 0.26, 0.22, 0.24)


def test_crop_version() -> None:
    assert CROP_VERSION == "passport-crop-v2"


def test_output_keeps_3x4_aspect() -> None:
    crop = passport_crop(_synthetic_alpha(), (640, 800), face_box_normalized=_face_box())
    assert abs(crop.aspect - PORTRAIT_ASPECT) < 0.02


def test_crop_expands_beyond_face_only_area() -> None:
    crop = passport_crop(_synthetic_alpha(), (640, 800), face_box_normalized=_face_box())
    _fx, _fy, fw, _fh = _face_box()
    face_width = fw * 640
    # Shoulder-based frame must be wider than the bare face rectangle.
    assert crop.width > face_width * 1.3


def test_top_margin_above_head_and_hair() -> None:
    alpha = _synthetic_alpha()
    crop = passport_crop(alpha, (640, 800), face_box_normalized=_face_box())
    _fx, fy, _fw, _fh = _face_box()
    head_top = fy * 800
    # Space above the face box top.
    assert crop.y0 <= head_top - 0.08 * crop.height
    # And the top boundary stays above the highest visible hair (matte top), never clipping it.
    fg_top = int(np.argmax(np.any(alpha > 0.5, axis=1)))
    assert crop.y0 <= fg_top


def test_lateral_shoulder_space() -> None:
    alpha = _synthetic_alpha()
    crop = passport_crop(alpha, (640, 800), face_box_normalized=_face_box())
    fg_x0 = int(np.argmax(np.any(alpha > 0.5, axis=0)))
    fg_x1 = int(alpha.shape[1] - np.argmax(np.any(alpha > 0.5, axis=0)[::-1]))
    # Both shoulders have visible side margin.
    assert crop.x0 <= fg_x0 - 0.05 * crop.width
    assert crop.x1 >= fg_x1 + 0.05 * crop.width


def test_crop_does_not_clip_matte_foreground_top() -> None:
    alpha = _synthetic_alpha()
    crop = passport_crop(alpha, (640, 800), face_box_normalized=_face_box())
    fg_top = int(np.argmax(np.any(alpha > 0.5, axis=1)))
    assert crop.y0 <= fg_top - 2


def test_deterministic_output() -> None:
    alpha = _synthetic_alpha()
    first = passport_crop(alpha, (640, 800), face_box_normalized=_face_box())
    second = passport_crop(alpha, (640, 800), face_box_normalized=_face_box())
    assert first == second


def test_keeps_upper_shoulders() -> None:
    alpha = _synthetic_alpha()
    crop = passport_crop(alpha, (640, 800), face_box_normalized=_face_box())
    fg_bottom = int(alpha.shape[0] - np.argmax(np.any(alpha > 0.5, axis=1)[::-1]))
    # The crop includes the shoulder line (upper shoulders); the widest shoulder edge may sit just
    # at/below the frame bottom, with hair still preserved above.
    assert crop.y1 >= fg_bottom - int(0.05 * crop.height)
