"""Browser session / capture / portrait / submit API (M5.8 §12, §13, §19, §20-23).

All mutations require an ACTIVE browser session (cookie) plus a session-bound CSRF token. The
production portrait and submit paths require a persisted canonical ``DecisionOutcome.PASS``; the
experimental VLM result is never consulted for submission.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from app.api.deps import (
    require_active_session,
    require_csrf,
    resolve_session_record,
)
from app.api.v1.experiments import _read_bounded, _validate_image
from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations import ConsumerRegistry
from app.integrations.attempts import (
    AttemptResult,
    AttemptUploadRejectedError,
    AttemptValidationError,
    read_attempt_summary,
    register_attempt,
)
from app.integrations.browser_session import launch_outcome_cookie_name
from app.integrations.callback import (
    CallbackTerminalError,
    CallbackTransportError,
    build_callback_event_id,
    build_callback_payload,
    send_callback,
    utc_now_iso,
    validate_redirect_url,
)
from app.integrations.consumers import ConsumerProfile
from app.integrations.store import IntegrationIndexStore
from app.observability import metrics
from app.portrait import PortraitErrorCode, PortraitProcessingError, PortraitProcessor
from app.transactions import ArtifactType, TransactionStatus
from app.transactions.decisions import has_canonical_pass, read_decision
from app.transactions.store import (
    TERMINAL_TRANSACTION_STATUSES,
    TransactionFileStore,
    sha256_hex,
)

router = APIRouter(prefix="/browser", tags=["browser"])

#: Callback state path (transaction-relative). Stores only safe metadata, never Base64/body/secret.
CALLBACK_STATE_PATH = "callback/decision-callback.json"


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _store(request: Request) -> TransactionFileStore:
    store = getattr(request.app.state, "transaction_store", None)
    if store is None:
        raise ApiError(code="TECHNICAL_ERROR", message="Storage not configured", status_code=500)
    return cast(TransactionFileStore, store)


def _index(request: Request) -> IntegrationIndexStore:
    index = getattr(request.app.state, "integration_index_store", None)
    if index is None:
        raise ApiError(code="TECHNICAL_ERROR", message="Index not configured", status_code=500)
    return cast(IntegrationIndexStore, index)


def _registry(request: Request) -> ConsumerRegistry:
    return cast(ConsumerRegistry, request.app.state.consumer_registry)


def _profile_for_tx(request: Request, consumer_id: str) -> ConsumerProfile | None:
    return _registry(request).get(consumer_id)


def _consumer_for_tx(request: Request, internal_tx_id: str) -> str:
    try:
        metadata = _store(request).read_transaction_json(internal_tx_id)
        value = metadata.get("consumer_id", "unknown")
        return str(value) if value else "unknown"
    except Exception:
        return "unknown"


def _max_attempts_for_tx(request: Request, internal_tx_id: str, default: int) -> int:
    profile = _profile_for_tx(request, _consumer_for_tx(request, internal_tx_id))
    if profile is not None and profile.max_attempts > 0:
        return profile.max_attempts
    return default


def _status_str(status: str | None) -> str:
    if status is None:
        return ""
    try:
        return TransactionStatus(status).value
    except ValueError:
        return TransactionStatus.TECHNICAL_ERROR.value


def _terminal_blocked(request: Request, internal_tx_id: str) -> None:
    status = _status_str(_store(request).read_transaction_json(internal_tx_id).get("status"))
    if status in {s.value for s in TERMINAL_TRANSACTION_STATUSES}:
        raise ApiError(
            code="TRANSACTION_TERMINAL",
            message="This transaction is in a terminal state",
            status_code=409,
        )


@router.get("/session")
def browser_session(request: Request) -> Response:
    settings = _settings(request)
    # Non-sensitive launch outcome set by redemption for INVALID/EXPIRED tokens (consumed once).
    outcome = request.cookies.get(launch_outcome_cookie_name(), "")
    if outcome in ("INVALID", "EXPIRED"):
        state = outcome.lower()
        response = JSONResponse({"state": state, "submission_ready": False})
        response.delete_cookie(launch_outcome_cookie_name(), path="/")
        return response

    record = resolve_session_record(request)
    if record is None:
        return JSONResponse({"state": "invalid", "submission_ready": False})

    internal_tx_id = record["transaction_id"]
    mode = record.get("mode")
    if mode == "TERMINAL":
        terminal_state = record.get("terminal_state")
        state = (
            "completed" if terminal_state == TransactionStatus.COMPLETED.value else "attempt_limit"
        )
        return JSONResponse(
            {"state": state, "submission_ready": False, "terminal_state": terminal_state}
        )

    attempts = read_attempt_summary(_store(request), internal_tx_id, settings.capture_attempt_limit)
    submission_ready = has_canonical_pass(_store(request), internal_tx_id) and _portrait_ready(
        _store(request), internal_tx_id
    )
    return JSONResponse(
        {
            "state": "active",
            "submission_ready": submission_ready,
            "attempt_count": attempts["attempt_count"],
            "max_attempts": _max_attempts_for_tx(
                request, internal_tx_id, settings.capture_attempt_limit
            ),
            "reason_codes": attempts["reason_codes"],
        }
    )


@router.post("/attempts")
def browser_attempts(
    request: Request,
    attempt_id: str = Form(...),
    result: str = Form(""),
    reason_code: str = Form(""),
) -> Response:
    record = require_active_session(request)
    require_csrf(request, record)
    internal_tx_id = record["transaction_id"]
    _terminal_blocked(request, internal_tx_id)
    try:
        attempt: AttemptResult = register_attempt(
            _settings(request),
            _store(request),
            internal_tx_id,
            attempt_id=attempt_id,
            result=result or None,
            reason_code=reason_code or None,
            max_attempts=_max_attempts_for_tx(
                request, internal_tx_id, _settings(request).capture_attempt_limit
            ),
        )
    except AttemptValidationError as exc:
        raise ApiError(
            code="DISALLOWED_REASON", message="Disallowed reason code", status_code=400
        ) from exc
    metrics.record_capture_attempt(_consumer_for_tx(request, internal_tx_id))
    return JSONResponse(_attempt_response(attempt))


@router.post("/capture")
async def browser_capture(
    request: Request,
    attempt_id: str = Form(...),
    selected_image: UploadFile = File(...),  # noqa: B008
    capture_config_version: str = Form(""),
    quality_config_version: str = Form(""),
) -> Response:
    record = require_active_session(request)
    require_csrf(request, record)
    internal_tx_id = record["transaction_id"]
    _terminal_blocked(request, internal_tx_id)
    settings = _settings(request)
    store = _store(request)

    data = await _read_bounded(selected_image, settings.vlm_max_single_image_bytes)
    mime = _validate_image(data, selected_image.content_type or "image/jpeg")

    # Register the attempt (capture path). Same attempt_id may already be recorded via /attempts.
    # mark_uploaded enforces one upload per attempt (a second upload for the same id is rejected).
    try:
        attempt = register_attempt(
            settings,
            store,
            internal_tx_id,
            attempt_id=attempt_id,
            result=None,
            reason_code=None,
            max_attempts=_max_attempts_for_tx(
                request, internal_tx_id, settings.capture_attempt_limit
            ),
            mark_uploaded=True,
        )
    except AttemptUploadRejectedError as exc:
        raise ApiError(
            code="UPLOAD_ALREADY_RECORDED",
            message="This attempt already uploaded a selected original",
            status_code=409,
        ) from exc
    if attempt.terminal:
        return JSONResponse(_attempt_response(attempt), status_code=409)

    store.write_artifact(
        internal_tx_id,
        ArtifactType.SELECTED_ORIGINAL_CAPTURE,
        data,
        content_type=mime,
    )
    store.write_json(
        internal_tx_id,
        "capture/capture.json",
        {
            "transaction_id": internal_tx_id,
            "mime_type": mime,
            "size_bytes": len(data),
            "sha256": sha256_hex(data),
            "capture_config_version": capture_config_version,
            "quality_config_version": quality_config_version,
        },
    )
    store.update_transaction_status(internal_tx_id, TransactionStatus.CAPTURE_READY.value)
    metrics.record_capture_attempt(_consumer_for_tx(request, internal_tx_id))
    return JSONResponse(_attempt_response(attempt))


@router.post("/portrait")
async def browser_portrait(request: Request, face_box: str = Form("")) -> Response:
    record = require_active_session(request)
    require_csrf(request, record)
    internal_tx_id = record["transaction_id"]
    _terminal_blocked(request, internal_tx_id)
    settings = _settings(request)
    store = _store(request)
    _require_canonical_pass(request, internal_tx_id)
    if not settings.portrait_processing_enabled:
        raise PortraitProcessingError(
            PortraitErrorCode.PORTRAIT_PROCESSING_FAILED, "portrait processing is disabled"
        )
    from app.transactions import ArtifactReference

    source_ref = ArtifactReference(
        transaction_id=internal_tx_id,
        artifact_type=ArtifactType.SELECTED_ORIGINAL_CAPTURE,
        relative_path="capture/selected-original.jpg",
        content_type="image/jpeg",
    )
    processor = PortraitProcessor(
        settings, store, segmentation=getattr(request.app.state, "portrait_segmentation", None)
    )
    result = await processor.process(source_ref, internal_tx_id)
    return JSONResponse(
        {
            "status": result.status,
            "output_artifact": result.output_artifact.relative_path,
            "sha256": result.output_artifact.sha256,
        }
    )


@router.get("/portrait")
def browser_portrait_image(request: Request) -> Response:
    record = require_active_session(request)
    require_csrf(request, record)
    internal_tx_id = record["transaction_id"]
    store = _store(request)
    path = "portrait/processed.jpg"
    if not store.artifact_exists(internal_tx_id, path):
        raise ApiError(code="PORTRAIT_NOT_READY", message="Portrait is not ready", status_code=404)
    data = store.read_artifact(internal_tx_id, path)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/submit")
async def browser_submit(request: Request) -> Response:
    record = require_active_session(request)
    require_csrf(request, record)
    internal_tx_id = record["transaction_id"]
    store = _store(request)
    settings = _settings(request)

    # Serialize the whole submit (state check + callback + status/state write) per transaction so
    # concurrent Submits for the same transaction cannot double-deliver or overwrite each other.
    with store.lock_transaction(internal_tx_id):
        status = _status_str(store.read_transaction_json(internal_tx_id).get("status"))
        if status == TransactionStatus.COMPLETED.value:
            raise ApiError(
                code="TRANSACTION_COMPLETED", message="Already completed", status_code=409
            )
        if status in {s.value for s in TERMINAL_TRANSACTION_STATUSES}:
            raise ApiError(code="TRANSACTION_TERMINAL", message="Terminal state", status_code=409)

        decision = read_decision(store, internal_tx_id)
        if decision is None or not has_canonical_pass(store, internal_tx_id):
            metrics.record_submit("not_ready")
            raise ApiError(
                code="NOT_READY",
                message="A canonical decision is not yet available",
                status_code=412,
            )

        portrait_bytes = _read_portrait_with_integrity(request, internal_tx_id)

        # ---- idempotent callback delivery ----
        metadata = store.read_transaction_json(internal_tx_id)
        consumer_id = str(metadata.get("consumer_id", ""))
        external_tx_id = str(metadata.get("external_transaction_id", ""))
        profile = _profile_for_tx(request, consumer_id)
        if profile is None:
            raise ApiError(
                code="INTEGRATION_NOT_CONFIGURED",
                message="Consumer not configured",
                status_code=503,
            )

        event_id = build_callback_event_id(consumer_id, external_tx_id)
        cb_state = _read_callback_state(store, internal_tx_id)
        if cb_state.get("state") == "ACKNOWLEDGED":
            # Double-Submit dedup: reuse the stored validated redirect URL without re-calling.
            metrics.record_submit("duplicate")
            return JSONResponse({"redirect_url": cb_state.get("redirect_url")})

        payload = build_callback_payload(
            event_id=event_id,
            external_transaction_id=external_tx_id,
            decision_id=decision.decision_id,
            processed_jpeg=portrait_bytes,
            occurred_at=utc_now_iso(),
        )

        try:
            delivery = await send_callback(settings, profile, payload)
        except CallbackTransportError as exc:
            _write_callback_state(
                store,
                internal_tx_id,
                {
                    "event_id": event_id,
                    "state": "FAILED",
                    "retryable": True,
                    "updated_at": utc_now_iso(),
                },
            )
            store.update_transaction_status(internal_tx_id, TransactionStatus.CALLBACK_FAILED.value)
            metrics.record_callback(consumer_id, "transient_failed", 0.0)
            metrics.record_submit("callback_failed")
            raise ApiError(
                code="CALLBACK_FAILED", message="Callback failed; please retry", status_code=502
            ) from exc
        except CallbackTerminalError as exc:
            _write_callback_state(
                store,
                internal_tx_id,
                {
                    "event_id": event_id,
                    "state": "FAILED",
                    "retryable": False,
                    "updated_at": utc_now_iso(),
                },
            )
            store.update_transaction_status(internal_tx_id, TransactionStatus.CALLBACK_FAILED.value)
            metrics.record_callback(consumer_id, "terminal_failed", 0.0)
            metrics.record_submit("callback_failed")
            raise ApiError(
                code="CALLBACK_FAILED", message="Callback failed", status_code=502
            ) from exc

        if not delivery.redirect_url or not validate_redirect_url(
            profile,
            delivery.redirect_url,
            local=settings.app_env in ("local", "test", "development"),
        ):
            _write_callback_state(
                store,
                internal_tx_id,
                {
                    "event_id": event_id,
                    "state": "FAILED",
                    "retryable": False,
                    "updated_at": utc_now_iso(),
                },
            )
            store.update_transaction_status(internal_tx_id, TransactionStatus.CALLBACK_FAILED.value)
            metrics.record_callback(consumer_id, "terminal_failed", delivery.latency_ms / 1000.0)
            metrics.record_submit("invalid_redirect")
            raise ApiError(
                code="INVALID_REDIRECT",
                message="Consumer redirect could not be validated",
                status_code=502,
            )

        _write_callback_state(
            store,
            internal_tx_id,
            {
                "event_id": event_id,
                "state": "ACKNOWLEDGED",
                "redirect_url": delivery.redirect_url,
                "updated_at": utc_now_iso(),
            },
        )
        store.update_transaction_status(internal_tx_id, TransactionStatus.COMPLETED.value)
        _revoke_after_completion(request, internal_tx_id)
        metrics.record_callback(consumer_id, "acknowledged", delivery.latency_ms / 1000.0)
        metrics.record_submit("ready")
        return JSONResponse({"redirect_url": delivery.redirect_url})


def _require_canonical_pass(request: Request, internal_tx_id: str) -> None:
    if not has_canonical_pass(_store(request), internal_tx_id):
        raise ApiError(
            code="NOT_READY", message="A canonical decision is not yet available", status_code=412
        )


def _portrait_ready(store: TransactionFileStore, internal_tx_id: str) -> bool:
    return store.artifact_exists(internal_tx_id, "portrait/processed.jpg")


def _read_portrait_with_integrity(request: Request, internal_tx_id: str) -> bytes:
    store = _store(request)
    if not store.artifact_exists(internal_tx_id, "portrait/processed.jpg"):
        raise ApiError(code="PORTRAIT_NOT_READY", message="Portrait is not ready", status_code=412)
    data = store.read_artifact(internal_tx_id, "portrait/processed.jpg")
    if not data or not data.startswith(b"\xff\xd8\xff"):
        raise ApiError(
            code="PORTRAIT_INTEGRITY_FAILED",
            message="Portrait integrity check failed",
            status_code=412,
        )
    return data


def _read_callback_state(store: TransactionFileStore, internal_tx_id: str) -> dict[str, Any]:
    if not store.artifact_exists(internal_tx_id, CALLBACK_STATE_PATH):
        return {}
    try:
        data = store.read_json(internal_tx_id, CALLBACK_STATE_PATH)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_callback_state(
    store: TransactionFileStore, internal_tx_id: str, state: dict[str, Any]
) -> None:
    store.write_json(internal_tx_id, CALLBACK_STATE_PATH, state)


def _revoke_after_completion(request: Request, internal_tx_id: str) -> None:
    # Revoke the active browser session index so reopening uses the TERMINAL path.
    from app.integrations.browser_session import _ACTIVE_SESSION_PATH

    store = _store(request)
    index = _index(request)
    if store.artifact_exists(internal_tx_id, _ACTIVE_SESSION_PATH):
        try:
            data = store.read_json(internal_tx_id, _ACTIVE_SESSION_PATH)
            prev = data.get("session_hash")
            if isinstance(prev, str):
                index.delete_browser_session(prev)
        except Exception:
            pass


def _attempt_response(attempt: AttemptResult) -> dict[str, Any]:
    return {
        "attempt_count": attempt.attempt_count,
        "max_attempts": attempt.max_attempts,
        "warning": attempt.warning,
        "terminal": attempt.terminal,
        "status": attempt.status,
    }
