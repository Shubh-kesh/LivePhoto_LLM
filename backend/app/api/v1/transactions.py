"""Transaction-scoped artifact API (M5.7 §62-64, §97).

Controlled, narrow endpoints only:
- ``POST /api/v1/transactions`` creates the transaction folder FIRST and persists the selected
  original capture.
- ``GET  /api/v1/transactions/{id}/artifacts/{artifact_type}`` reads a known artifact type
  (no directory listing, no arbitrary filename input, root-confined).
- ``POST /api/v1/transactions/{id}/portrait`` triggers backend portrait processing when the
  stored VLM result is LIVE and portrait processing is enabled.

No generic file server, no absolute paths, no arbitrary file read. The frontend never touches the
filesystem.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.core.config import Settings
from app.portrait import PortraitErrorCode, PortraitProcessingError, PortraitProcessor
from app.transactions import (
    ARTIFACT_RELATIVE_PATHS,
    ArtifactNotFoundError,
    ArtifactReference,
    ArtifactType,
    TransactionFileStore,
    TransactionPathError,
    TransactionStorageError,
    is_valid_transaction_id,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

CONTENT_TYPES: dict[ArtifactType, str] = {
    ArtifactType.SELECTED_ORIGINAL_CAPTURE: "image/jpeg",
    ArtifactType.VLM_RESULT: "application/json",
    ArtifactType.PROCESSED_PORTRAIT: "image/jpeg",
    ArtifactType.PORTRAIT_PROCESSING_RESULT: "application/json",
}


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _store(request: Request) -> TransactionFileStore:
    store: TransactionFileStore | None = getattr(request.app.state, "transaction_store", None)
    if store is None:
        raise TransactionStorageError("transaction storage is not configured")
    return store


def _guard_experiment(request: Request) -> None:
    """Gate the legacy experiment transaction/portrait endpoints (M5.8 §1).

    These existed for the M5.7 VLM experiment (transaction created at capture upload). Under M5.8
    the production path creates the transaction at launch; this endpoint must not be a production
    bypass, so it is restricted to experiment availability.
    """
    from app.providers.vision import VlmError, VlmErrorCode

    if not _settings(request).vlm_experiment_available:
        raise VlmError(VlmErrorCode.VLM_DISABLED, "VLM experiment is not enabled")


def _tx_id_or_error(transaction_id: str) -> str:
    if not is_valid_transaction_id(transaction_id):
        raise TransactionPathError("invalid transaction id")
    return transaction_id


@router.post("")
async def create_transaction(
    request: Request,
    image: UploadFile = File(...),  # noqa: B008
    capture_config_version: str = Form(""),
    quality_config_version: str = Form(""),
) -> dict[str, Any]:
    """Create a transaction folder FIRST, then persist the selected original capture (M5.7 §2)."""
    settings = _settings(request)
    store = _store(request)
    _guard_experiment(request)
    from app.api.v1.experiments import _read_bounded, _validate_image

    data = await _read_bounded(image, settings.vlm_max_single_image_bytes)
    mime = _validate_image(data, image.content_type or "image/jpeg")

    transaction_id = uuid.uuid4().hex
    store.create_transaction(
        transaction_id,
        {
            "transaction_id": transaction_id,
            "created_at": _utc_now(),
            "app_version": settings.app_version,
            "capture_config_version": capture_config_version,
            "quality_config_version": quality_config_version,
            "status": "CREATED",
        },
    )
    capture_ref = store.write_artifact(
        transaction_id,
        ArtifactType.SELECTED_ORIGINAL_CAPTURE,
        data,
        content_type=mime,
    )
    store.write_json(
        transaction_id,
        "capture/capture.json",
        {
            "transaction_id": transaction_id,
            "capture_artifact": capture_ref.relative_path,
            "mime_type": mime,
            "size_bytes": len(data),
            "sha256": capture_ref.sha256,
            "capture_config_version": capture_config_version,
            "quality_config_version": quality_config_version,
        },
    )
    store.update_transaction_status(transaction_id, "CAPTURE_READY")

    return {
        "transaction_id": transaction_id,
        "status": "CAPTURE_READY",
        "capture_artifact": {
            "relative_path": capture_ref.relative_path,
            "content_type": capture_ref.content_type,
            "size_bytes": capture_ref.size_bytes,
            "sha256": capture_ref.sha256,
        },
    }


@router.get("/{transaction_id}/artifacts/{artifact_type}")
def get_artifact(request: Request, transaction_id: str, artifact_type: str) -> Response:
    """Controlled artifact read for known artifact types only (M5.7 §62-64)."""
    _guard_experiment(request)
    _tx_id_or_error(transaction_id)
    store = _store(request)
    try:
        artifact_kind = ArtifactType(artifact_type.upper())
    except ValueError as exc:
        raise TransactionPathError("unknown artifact type") from exc
    relative_path = ARTIFACT_RELATIVE_PATHS[artifact_kind]
    if not store.transaction_exists(transaction_id):
        raise ArtifactNotFoundError("transaction not found")
    try:
        data = store.read_artifact(transaction_id, relative_path)
    except ArtifactNotFoundError:
        raise
    content_type = CONTENT_TYPES[artifact_kind]
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if artifact_kind in (ArtifactType.PROCESSED_PORTRAIT, ArtifactType.SELECTED_ORIGINAL_CAPTURE):
        headers["Content-Type"] = content_type
        return Response(content=data, headers=headers, media_type=content_type)
    return Response(content=data, headers=headers, media_type=content_type)


@router.post("/{transaction_id}/portrait")
async def process_portrait(
    request: Request,
    transaction_id: str,
    face_box: str = Form(""),  # "x,y,w,h" normalized, optional
) -> dict[str, Any]:
    """Trigger backend portrait processing only when the stored VLM result is LIVE (M5.7 §21)."""
    _guard_experiment(request)
    _tx_id_or_error(transaction_id)
    store = _store(request)
    if not store.transaction_exists(transaction_id):
        raise ArtifactNotFoundError("transaction not found")

    settings = _settings(request)
    if not settings.portrait_processing_enabled:
        raise PortraitProcessingError(
            PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
            "portrait processing is disabled",
        )

    vlm_relative = ARTIFACT_RELATIVE_PATHS[ArtifactType.VLM_RESULT]
    if not store.artifact_exists(transaction_id, vlm_relative):
        raise PortraitProcessingError(
            PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
            "no VLM result stored for this transaction",
        )
    vlm_result = store.read_json(transaction_id, vlm_relative)
    if vlm_result.get("classification") != "LIVE":
        raise PortraitProcessingError(
            PortraitErrorCode.PORTRAIT_PROCESSING_FAILED,
            "portrait processing requires a LIVE experimental result",
        )

    face_box_normalized: tuple[float, float, float, float] | None = None
    if face_box.strip():
        parts = face_box.split(",")
        if len(parts) == 4:
            try:
                face_box_normalized = tuple(float(p) for p in parts)  # type: ignore[assignment]
            except ValueError:
                face_box_normalized = None

    source_ref = ArtifactReference(
        transaction_id=transaction_id,
        artifact_type=ArtifactType.SELECTED_ORIGINAL_CAPTURE,
        relative_path=ARTIFACT_RELATIVE_PATHS[ArtifactType.SELECTED_ORIGINAL_CAPTURE],
        content_type="image/jpeg",
    )

    processor = PortraitProcessor(
        settings,
        store,
        segmentation=getattr(request.app.state, "portrait_segmentation", None),
    )
    result = await processor.process(
        source_ref,
        transaction_id,
        face_box_normalized=face_box_normalized,
    )
    return {
        "status": result.status,
        "transaction_id": transaction_id,
        "output_artifact": {
            "relative_path": result.output_artifact.relative_path,
            "content_type": result.output_artifact.content_type,
            "size_bytes": result.output_artifact.size_bytes,
            "sha256": result.output_artifact.sha256,
        },
        "processor_version": result.processor_version,
        "crop_version": result.crop_version,
        "background_mode": result.background_mode,
        "background_color": result.background_color,
        "width": result.width,
        "height": result.height,
        "processing_ms": result.processing_ms,
    }


def _utc_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()
