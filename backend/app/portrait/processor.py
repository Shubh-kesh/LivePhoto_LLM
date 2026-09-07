"""Backend portrait processor (M5.7 §23-27, §42-47, §60-61, §71-77).

Pipeline: decode selected original -> person matting (soft alpha) -> edge refinement -> passport
crop -> configurable background composite -> high-quality JPEG encode -> persist under the
transaction folder. Runs backend-side only; the frontend only displays the result.

Failures are typed technical errors (PORTRAIT_PROCESSING_FAILED); the original image is never
returned as a successful processed portrait (no silent fallback, M5.7 §45).
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.core.logging import get_logger
from app.portrait.background import composite_solid, parse_background_color
from app.portrait.crop import CROP_VERSION, CropBox, passport_crop
from app.portrait.errors import (
    PortraitErrorCode,
    PortraitProcessingError,
)
from app.portrait.segmentation import OnnxPortraitSegmentation, SegmentationProvider
from app.transactions import (
    ARTIFACT_RELATIVE_PATHS,
    ArtifactReference,
    ArtifactType,
    TransactionFileStore,
)

logger = get_logger("livephoto.portrait")

PROCESSOR_VERSION = "portrait-processor-v1"
ALPHA_REFINE_RADIUS = 1.0


@dataclass(frozen=True)
class PortraitProcessingResult:
    status: str
    source_artifact: ArtifactReference
    output_artifact: ArtifactReference
    processor_version: str
    crop_version: str
    background_mode: str
    background_color: str
    width: int
    height: int
    processing_ms: int
    model: dict[str, str]
    crop_box: CropBox


class PortraitProcessor:
    def __init__(
        self,
        settings: Settings,
        store: TransactionFileStore,
        segmentation: SegmentationProvider | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._segmentation = segmentation

    @property
    def enabled(self) -> bool:
        return self._settings.portrait_processing_enabled

    def _provider(self) -> SegmentationProvider:
        if self._segmentation is not None:
            return self._segmentation
        if not self._settings.portrait_model_path:
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_MODEL_UNAVAILABLE,
                "portrait model is not configured (PORTRAIT_MODEL_PATH)",
            )
        return OnnxPortraitSegmentation(
            self._settings.portrait_model_path,
            expected_sha256=self._settings.portrait_model_sha256,
        )

    async def process(
        self,
        source: ArtifactReference,
        transaction_id: str,
        *,
        face_box_normalized: tuple[float, float, float, float] | None = None,
    ) -> PortraitProcessingResult:
        if not self.enabled:
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
                "portrait processing is disabled",
            )
        if not self._store.transaction_exists(transaction_id):
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
                "transaction does not exist",
            )

        self._store.update_transaction_status(transaction_id, "PORTRAIT_PROCESSING")
        started = time.perf_counter()
        model = self._provider().info
        logger.info(
            "portrait_processing_started",
            transaction_id=transaction_id,
            source_artifact=source.relative_path,
            processor_version=PROCESSOR_VERSION,
            model=model.get("name"),
            model_hash=model.get("sha256"),
            background_mode=self._settings.portrait_background_mode,
            background_color=self._settings.portrait_background_color,
            crop_version=CROP_VERSION,
        )
        try:
            image_bytes = self._store.read_artifact(transaction_id, source.relative_path)
            image = self._decode(image_bytes)
            alpha = self._provider().predict_alpha(image)
            alpha = self._refine_alpha(alpha)
            crop_box = passport_crop(
                alpha,
                (image.width, image.height),
                face_box_normalized=face_box_normalized,
            )
            background_rgb = parse_background_color(self._settings.portrait_background_color)

            crop = image.crop((crop_box.x0, crop_box.y0, crop_box.x1, crop_box.y1))
            crop_alpha = alpha[crop_box.y0 : crop_box.y1, crop_box.x0 : crop_box.x1]
            foreground_rgb = np.asarray(crop.convert("RGB"))
            composed = composite_solid(foreground_rgb, crop_alpha, background_rgb)
            output = Image.fromarray(composed, mode="RGB")

            encoded = self._encode(output)
            output_ref = self._store.write_artifact(
                transaction_id,
                ArtifactType.PROCESSED_PORTRAIT,
                encoded,
                content_type="image/jpeg",
            )

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._store.write_json(
                transaction_id,
                ARTIFACT_RELATIVE_PATHS[ArtifactType.PORTRAIT_PROCESSING_RESULT],
                self._build_metadata(
                    transaction_id,
                    source,
                    output_ref,
                    crop_box,
                    elapsed_ms,
                    model,
                    output.width,
                    output.height,
                ),
            )
            self._store.update_transaction_status(transaction_id, "PORTRAIT_READY")

            result = PortraitProcessingResult(
                status="SUCCESS",
                source_artifact=source,
                output_artifact=output_ref,
                processor_version=PROCESSOR_VERSION,
                crop_version=CROP_VERSION,
                background_mode=self._settings.portrait_background_mode,
                background_color=self._settings.portrait_background_color,
                width=output.width,
                height=output.height,
                processing_ms=elapsed_ms,
                model=model,
                crop_box=crop_box,
            )
            logger.info(
                "portrait_processing_completed",
                transaction_id=transaction_id,
                source_artifact=source.relative_path,
                output_artifact=output_ref.relative_path,
                processor_version=PROCESSOR_VERSION,
                model=model.get("name"),
                model_hash=model.get("sha256"),
                background_mode=self._settings.portrait_background_mode,
                background_color=self._settings.portrait_background_color,
                crop_version=CROP_VERSION,
                processing_ms=elapsed_ms,
                width=output.width,
                height=output.height,
            )
            return result
        except Exception as exc:
            if isinstance(exc, PortraitProcessingError):
                self._record_failure(transaction_id, source, model, exc.code.value)
                raise
            if isinstance(exc, (UnidentifiedImageError, OSError, ValueError)):
                self._record_failure(transaction_id, source, model, "decode_or_pipeline_failed")
                raise PortraitProcessingError(
                    PortraitErrorCode.PORTRAIT_INVALID_SOURCE,
                    "portrait source image could not be processed",
                ) from exc
            self._record_failure(transaction_id, source, model, "unexpected")
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
                "portrait processing failed",
            ) from exc

    def _record_failure(
        self,
        transaction_id: str,
        source: ArtifactReference,
        model: dict[str, str],
        error_code: str,
    ) -> None:
        self._store.update_transaction_status(transaction_id, "TECHNICAL_ERROR")
        logger.info(
            "portrait_processing_failed",
            transaction_id=transaction_id,
            source_artifact=source.relative_path,
            processor_version=PROCESSOR_VERSION,
            model=model.get("name"),
            model_hash=model.get("sha256"),
            error_code=error_code,
            processing_ms=0,
        )

    def _decode(self, data: bytes) -> Image.Image:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise PortraitProcessingError(
                PortraitErrorCode.PORTRAIT_INVALID_SOURCE,
                "source image is corrupt or unsupported",
            ) from exc
        return image.convert("RGB")

    def _refine_alpha(self, alpha: np.ndarray) -> np.ndarray:
        from PIL import ImageFilter

        smoothed = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(radius=ALPHA_REFINE_RADIUS)
        )
        return np.asarray(smoothed, dtype=np.float32) / 255.0

    def _encode(self, image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self._settings.portrait_jpeg_quality)
        return buffer.getvalue()

    def _build_metadata(
        self,
        transaction_id: str,
        source: ArtifactReference,
        output: ArtifactReference,
        crop_box: CropBox,
        processing_ms: int,
        model: dict[str, str],
        output_width: int,
        output_height: int,
    ) -> dict[str, object]:
        return {
            "status": "SUCCESS",
            "processor": "portrait-processor",
            "processor_version": PROCESSOR_VERSION,
            "model_name": model.get("name"),
            "model_hash": model.get("sha256"),
            "source_artifact": source.relative_path,
            "output_artifact": output.relative_path,
            "crop_version": CROP_VERSION,
            "crop_coordinates": {
                "x0": crop_box.x0,
                "y0": crop_box.y0,
                "x1": crop_box.x1,
                "y1": crop_box.y1,
                "normalized": list(crop_box.normalized),
            },
            "background_mode": self._settings.portrait_background_mode,
            "background_color": self._settings.portrait_background_color,
            "output_dimensions": {"width": output_width, "height": output_height},
            "output_format": self._settings.portrait_output_format,
            "jpeg_quality": self._settings.portrait_jpeg_quality,
            "processing_ms": processing_ms,
            "timestamp": _utc_now(),
        }


def _utc_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()
