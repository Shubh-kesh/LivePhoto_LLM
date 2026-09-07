"""Person matting / segmentation provider (M5.7 §48-57).

Dedicated deterministic segmentation (MODNet portrait matting via ONNX Runtime) — never a VLM.
The provider returns a soft alpha matte (0..1). A deterministic fake is available for tests.

Model assets are provisioned explicitly (see scripts/provision-portrait-model.sh) into a
git-ignored directory and pinned by SHA-256; weights are never downloaded per-request and never
committed to git (M5.7 §51-53).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from app.portrait.errors import (
    PortraitErrorCode,
    PortraitProcessingError,
)
from app.transactions import sha256_hex

DEFAULT_INPUT_SIZE = 512


class SegmentationProvider(Protocol):
    """Produces a soft alpha matte (0..1) for the primary portrait subject."""

    def predict_alpha(self, image: Image.Image) -> np.ndarray: ...

    @property
    def info(self) -> dict[str, str]: ...


@dataclass(frozen=True)
class ModelInfo:
    name: str
    source: str
    license: str
    version: str
    sha256: str


class OnnxPortraitSegmentation:
    """MODNet photographic portrait matting via ONNX Runtime (CPU-first)."""

    def __init__(
        self,
        model_path: str,
        *,
        expected_sha256: str = "",
        input_size: int = DEFAULT_INPUT_SIZE,
    ) -> None:
        import onnxruntime as ort

        raw = Path(model_path).read_bytes()
        self._expected_sha256 = expected_sha256 or sha256_hex(raw)
        if expected_sha256 and sha256_hex(raw) != expected_sha256.lower():
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_MODEL_INTEGRITY,
                "portrait model SHA-256 mismatch",
            )
        self._input_size = input_size
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name

    @property
    def info(self) -> dict[str, str]:
        return {
            "name": "MODNet photographic portrait matting",
            "backend": "onnxruntime",
            "sha256": self._expected_sha256,
        }

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        rgb = image.convert("RGB")
        original = (rgb.width, rgb.height)
        resized = rgb.resize((self._input_size, self._input_size), Image.Resampling.BILINEAR)
        tensor = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = tensor.transpose(2, 0, 1)[None, ...]  # (1,3,H,W)
        try:
            raw = self._session.run([self._output_name], {self._input_name: tensor})[0]
        except Exception as exc:
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
                "portrait segmentation inference failed",
            ) from exc
        alpha = np.asarray(raw).squeeze()
        if alpha.ndim != 2:
            alpha = alpha[0]
        alpha = np.clip(alpha.astype(np.float32), 0.0, 1.0)
        resized_alpha: np.ndarray = np.asarray(
            Image.fromarray((alpha * 255).astype(np.uint8)).resize(original)
        )
        return resized_alpha.astype(np.float32) / 255.0


class FakePortraitSegmentation:
    """Deterministic segmentation for unit tests: a centered elliptical matte."""

    def __init__(self, *, fail: bool = False, background_ratio: float = 0.3) -> None:
        self._fail = fail
        self._background_ratio = background_ratio

    @property
    def info(self) -> dict[str, str]:
        return {"name": "fake-portrait-matting", "backend": "test", "sha256": "fake"}

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        if self._fail:
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
                "fake segmentation failure",
            )
        width, height = image.size
        yy, xx = np.mgrid[0:height, 0:width]
        cx, cy = width / 2, height / 2
        rx, ry = width * (1 - self._background_ratio), height * (1 - self._background_ratio)
        distance = np.sqrt(((xx - cx) / max(rx, 1)) ** 2 + ((yy - cy) / max(ry, 1)) ** 2)
        alpha: np.ndarray = np.clip(1.0 - distance, 0.0, 1.0).astype(np.float32)
        return alpha
