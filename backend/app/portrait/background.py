"""Background replacement (M5.7 §40-41, §57).

M5.7 supports ``solid`` only (config-driven ``#RRGGBB``). A future-compatible seam; no blur/custom
scenes. Edge compositing keeps hair soft (no crude binary thresholding) and reduces halo/color
spill by blending with the soft alpha matte.
"""

from __future__ import annotations

import re

import numpy as np

COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def parse_background_color(value: str) -> tuple[int, int, int]:
    if not COLOR_PATTERN.fullmatch(value):
        raise ValueError("background color must be #RRGGBB")
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def composite_solid(
    foreground_rgb: np.ndarray,
    alpha: np.ndarray,
    background_rgb: tuple[int, int, int],
) -> np.ndarray:
    """Composite a soft-alpha foreground over a solid background color.

    ``alpha`` is normalized to ``foreground_rgb`` shape (H, W). Uses premultiplied blending so
    semi-transparent hair edges remain natural instead of dark haloed cutouts.
    """
    alpha = np.clip(alpha, 0.0, 1.0)[..., None]
    background = np.asarray(background_rgb, dtype=np.float32)[None, None, :]
    blended = foreground_rgb.astype(np.float32) * alpha + background * (1.0 - alpha)
    result: np.ndarray = np.clip(blended, 0.0, 255.0).astype(np.uint8)
    return result
