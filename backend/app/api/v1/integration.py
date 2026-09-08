"""Consumer S2S integration API (M5.8 §3, §8, §16).

- ``POST /integration/launch-sessions``                     create launch (folder before capture).
- ``POST /integration/transactions/{external}/launch-sessions`` reissue (same internal tx).
- ``GET  /integration/transactions/{external}/status``      consumer-isolated status lookup.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.api.deps import _index, _settings, _store
from app.core.errors import ApiError
from app.integrations import ConsumerConfigError, ConsumerProfile, ConsumerRegistry
from app.integrations.launch import (
    LaunchResult,
    LaunchSessionRequest,
    create_launch,
    reissue_launch,
)
from app.integrations.s2s_auth import authenticate_s2s
from app.integrations.status import resolve_status
from app.observability import metrics
from app.transactions.store import ArtifactNotFoundError, TransactionExistsError

router = APIRouter(prefix="/integration", tags=["integration"])


def _registry(request: Request) -> ConsumerRegistry:
    return cast(ConsumerRegistry, request.app.state.consumer_registry)


def _authenticated_consumer(request: Request, source: str) -> ConsumerProfile:
    return authenticate_s2s(
        _settings(request),
        _registry(request),
        authorization_header=request.headers.get("authorization", ""),
        dev_auth_header=request.headers.get("x-livephoto-dev-auth", ""),
        requested_source=source,
    )


@router.post("/launch-sessions")
def launch_session(request: Request, body: LaunchSessionRequest) -> Response:
    profile = _authenticated_consumer(request, body.source)
    if not profile.request_policy_allows(
        ocr_required=body.ocr_required,
        camera_config=body.camera_config,
        white_background=body.white_background,
        output_file_format=body.output_file_format,
    ):
        metrics.record_launch_session(profile.consumer_id, "policy_denied")
        raise ApiError(
            code="REQUEST_POLICY_VIOLATION",
            message="Requested options are not permitted by the consumer profile",
            status_code=400,
        )
    try:
        result = create_launch(_settings(request), _store(request), _index(request), profile, body)
    except TransactionExistsError:
        metrics.record_launch_session(profile.consumer_id, "duplicate")
        raise ApiError(
            code="TRANSACTION_EXISTS",
            message="A transaction already exists for this consumer and external id",
            status_code=409,
        ) from None
    except ConsumerConfigError as exc:
        raise ApiError(
            code="INTEGRATION_NOT_CONFIGURED", message=str(exc), status_code=503
        ) from exc

    metrics.record_launch_session(profile.consumer_id, "created")
    return Response(
        content=_launch_payload(result),
        media_type="application/json",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/transactions/{external_transaction_id}/launch-sessions")
def reissue_launch_session(
    request: Request, external_transaction_id: str, source: str = ""
) -> Response:
    profile = _authenticated_consumer(request, source)
    try:
        result = reissue_launch(
            _settings(request), _store(request), _index(request), profile, external_transaction_id
        )
    except ArtifactNotFoundError:
        raise ApiError(code="NOT_FOUND", message="Transaction not found", status_code=404) from None
    metrics.record_launch_session(profile.consumer_id, "reissued")
    return Response(
        content=_launch_payload(result),
        media_type="application/json",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/transactions/{external_transaction_id}/status")
def transaction_status(
    request: Request, external_transaction_id: str, source: str = ""
) -> Response:
    profile = _authenticated_consumer(request, source)
    status = resolve_status(_store(request), _index(request), profile, external_transaction_id)
    if status is None:
        metrics.record_status_read(profile.consumer_id)
        raise ApiError(code="NOT_FOUND", message="Transaction not found", status_code=404)
    metrics.record_status_read(profile.consumer_id)
    import json

    return Response(
        content=json.dumps(status, sort_keys=True),
        media_type="application/json",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _launch_payload(result: LaunchResult) -> str:
    import json

    return json.dumps(
        {
            "transaction_id": result.external_transaction_id,
            "launch_session_id": result.launch_session_id,
            "launch_url": result.launch_url,
            "expires_at": result.expires_at,
            "expires_in_seconds": result.expires_in_seconds,
        },
        sort_keys=True,
    )
