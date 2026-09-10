"""Development-only VLM experiment endpoints (M4 §9-12, §15, §128).

- Bounded multipart upload of already-selected frames (never browser Base64 JSON).
- Refuses to operate unless VLM_EXPERIMENT_ENABLED=true AND the environment is not
  uat/production (M4 §11).
- No bank production APIs; no persistence of capture bytes.
"""

from __future__ import annotations

import io
import json
from datetime import UTC
from typing import Any, cast

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.core.config import Settings
from app.experiments.vlm import ExperimentEvaluateRequest, ExperimentResult, VlmEvaluationService
from app.experiments.vlm.frame_selection import FRAME_STRATEGIES, is_supported_strategy
from app.providers.vision import (
    VlmError,
    VlmErrorCode,
    available_providers,
    get_vision_provider,
)
from app.providers.vision.models import ImageInput

router = APIRouter(prefix="/experiments/vlm", tags=["experiments"])

JPEG_SIGNATURE = b"\xff\xd8\xff"
MAX_IMAGE_DIMENSION = 4096


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _guard(request: Request) -> None:
    settings = _settings(request)
    if not settings.vlm_experiment_available:
        raise VlmError(VlmErrorCode.VLM_DISABLED, "VLM experiment is not enabled")


def _validate_image(data: bytes, declared_mime: str) -> str:
    allowed = ("image/jpeg",)
    if declared_mime not in allowed:
        raise VlmError(VlmErrorCode.UNSUPPORTED_MEDIA_TYPE, "unsupported media type")
    if not data.startswith(JPEG_SIGNATURE):
        raise VlmError(VlmErrorCode.UNSUPPORTED_MEDIA_TYPE, "not a valid JPEG")
    if len(data) == 0:
        raise VlmError(VlmErrorCode.PROVIDER_BAD_REQUEST, "empty image")
    _verify_decodeable(data)
    return declared_mime


def _verify_decodeable(data: bytes) -> None:
    from PIL import Image, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
                raise VlmError(VlmErrorCode.REQUEST_TOO_LARGE, "image dimensions exceed limit")
            image.verify()
    except VlmError:
        raise
    except Image.DecompressionBombError as exc:
        raise VlmError(
            VlmErrorCode.REQUEST_TOO_LARGE, "image exceeds decompression limits"
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise VlmError(VlmErrorCode.UNSUPPORTED_MEDIA_TYPE, "image could not be decoded") from exc


async def _read_bounded(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise VlmError(VlmErrorCode.REQUEST_TOO_LARGE, "image exceeds the size limit")
    return data


@router.get("/providers")
def list_providers(request: Request) -> dict[str, object]:
    """Environment-permitted providers with non-sensitive descriptor info (M5.6 §26).

    Never returns API keys or internal service URLs.
    """
    _guard(request)
    settings = _settings(request)
    names = available_providers(settings)
    providers = [
        {
            "name": provider.info.provider_name,
            "model": provider.info.model_id,
            "provider_adapter_version": provider.info.provider_adapter_version,
            "max_images": provider.capabilities.max_images_per_request,
            "supports_structured_output": provider.capabilities.supports_structured_output,
            "supports_inline_images": provider.capabilities.supports_inline_images,
        }
        for provider in (get_vision_provider(settings, name) for name in names)
    ]
    return {
        "experiment_enabled": True,
        "environment": settings.app_env,
        "providers": providers,
        "default_provider": providers[0]["name"] if providers else None,
    }


@router.post("/evaluate")
async def evaluate_vlm(
    request: Request,
    strategy: str = Form(...),
    provider: str = Form(...),
    capture_config_version: str = Form(""),
    quality_config_version: str = Form(""),
    frame_selection_version: str = Form(""),
    mock_behavior: str = Form(""),
    transaction_id: str = Form(""),
    frames: list[UploadFile] = File(...),  # noqa: B008
) -> Any:
    _guard(request)
    settings = _settings(request)

    if not is_supported_strategy(strategy):
        raise VlmError(VlmErrorCode.PROVIDER_BAD_REQUEST, f"unsupported strategy '{strategy}'")
    expected_count = FRAME_STRATEGIES[strategy]
    if len(frames) != expected_count:
        raise VlmError(
            VlmErrorCode.PROVIDER_BAD_REQUEST,
            f"strategy '{strategy}' requires {expected_count} frame(s), got {len(frames)}",
        )
    if len(frames) > settings.vlm_max_frames:
        raise VlmError(VlmErrorCode.TOO_MANY_IMAGES, "too many images")

    image_inputs: list[ImageInput] = []
    total_bytes = 0
    for index, upload in enumerate(frames):
        data = await _read_bounded(upload, settings.vlm_max_single_image_bytes)
        total_bytes += len(data)
        if total_bytes > settings.vlm_max_total_image_bytes:
            raise VlmError(VlmErrorCode.REQUEST_TOO_LARGE, "total image bytes exceed the limit")
        mime = _validate_image(data, upload.content_type or "image/jpeg")
        image_inputs.append(ImageInput(bytes=data, mime_type=mime, sequence=index))

    experiment_request = ExperimentEvaluateRequest(
        strategy=strategy,
        capture_config_version=capture_config_version,
        quality_config_version=quality_config_version,
        frame_selection_version=frame_selection_version,
        provider=provider,
        mock_behavior=mock_behavior,
        frames=image_inputs,
    )

    service = VlmEvaluationService(settings)
    result = await service.evaluate(experiment_request)

    payload: dict[str, Any] = result.model_dump()
    if transaction_id:
        await _persist_vlm_result(request, settings, transaction_id, result)
        payload["transaction_id"] = transaction_id

    return payload


async def _persist_vlm_result(
    request: Request,
    settings: Settings,
    transaction_id: str,
    result: ExperimentResult,
) -> None:
    """Persist a normalized, safe VLM result under the transaction folder (M5.7 §20)."""
    from datetime import datetime

    from app.transactions import (
        ArtifactNotFoundError,
        ArtifactType,
        TransactionFileStore,
        TransactionStorageError,
        is_valid_transaction_id,
    )

    if not is_valid_transaction_id(transaction_id):
        raise TransactionStorageError("invalid transaction id")
    store: TransactionFileStore | None = getattr(request.app.state, "transaction_store", None)
    if store is None:
        raise TransactionStorageError("transaction storage is not configured")
    if not store.transaction_exists(transaction_id):
        raise ArtifactNotFoundError("transaction not found")

    normalized = {
        "provider": result.provider,
        "model": result.model,
        "strategy": result.frame_strategy,
        "classification": result.classification,
        "attack_medium": result.attack_medium,
        "self_reported_confidence": result.self_reported_confidence,
        "evidence_codes": list(result.evidence_codes),
        "subject_count": result.subject_count,
        "secondary_person_state": result.secondary_person_state,
        "latency_ms": result.latency_ms,
        "experiment_id": result.experiment_id,
        "request_id": request.scope.get("request_id", ""),
        "prompt_version": result.prompt_version,
        "schema_version": result.schema_version,
        "timestamp": datetime.now(UTC).isoformat(),
        "error": result.error.value if result.error else None,
    }
    store.write_artifact(
        transaction_id,
        ArtifactType.VLM_RESULT,
        json.dumps(normalized, sort_keys=True).encode("utf-8"),
        content_type="application/json",
    )
    store.update_transaction_status(transaction_id, "VLM_EVALUATED")
