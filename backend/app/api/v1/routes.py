"""V1 route definitions."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.v1.schemas import InfoResponse

router = APIRouter(tags=["info"])


@router.get("/info", response_model=InfoResponse, summary="Non-sensitive application info")
def get_info(request: Request) -> InfoResponse:
    settings = request.app.state.settings
    return InfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )
