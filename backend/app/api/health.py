"""Health endpoints (M1 §16).

``/health/live`` must not fail because a dependency is down; ``/health/ready`` runs registered
readiness checks (e.g. the database) that are added later. Responses never expose credentials,
host secrets, stack traces or internal security configuration.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.health import ReadinessResult

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: str = "ok"


class ReadyResponse(BaseModel):
    status: str
    checks: list[ReadinessResult] = []


@router.get("/health/live", response_model=LiveResponse, summary="Liveness probe")
def health_live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadyResponse}},
)
def health_ready(request: Request) -> JSONResponse | ReadyResponse:
    checks = [check() for check in request.app.state.ready_checks]
    ready = all(check.status == "ok" for check in checks)
    body = ReadyResponse(status="ready" if ready else "not_ready", checks=checks)
    if not ready:
        return JSONResponse(status_code=503, content=body.model_dump())
    return body
