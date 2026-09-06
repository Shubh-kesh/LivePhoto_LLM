"""Standard API error envelope and application error types.

Contract (M0 API_CONTRACT §7):
- stable machine-readable ``code``
- safe, user-presentable ``message`` (never stack traces)
- HTTP status
- ``request_id`` for correlation
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.providers.vision.errors import VlmError, VlmErrorCode

logger = logging.getLogger("livephoto.errors")

VLM_ERROR_STATUS: dict[VlmErrorCode, int] = {
    VlmErrorCode.VLM_DISABLED: 403,
    VlmErrorCode.PROVIDER_NOT_CONFIGURED: 503,
    VlmErrorCode.PROVIDER_AUTH_ERROR: 502,
    VlmErrorCode.PROVIDER_TIMEOUT: 503,
    VlmErrorCode.PROVIDER_RATE_LIMITED: 503,
    VlmErrorCode.PROVIDER_UNAVAILABLE: 503,
    VlmErrorCode.PROVIDER_BAD_REQUEST: 400,
    VlmErrorCode.REQUEST_TOO_LARGE: 413,
    VlmErrorCode.TOO_MANY_IMAGES: 400,
    VlmErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    VlmErrorCode.SCHEMA_VALIDATION_ERROR: 502,
    VlmErrorCode.PROVIDER_RESPONSE_ERROR: 502,
    VlmErrorCode.UNKNOWN_PROVIDER_ERROR: 502,
}


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str = ""


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class ApiError(Exception):
    """Application error with a stable machine-readable code and HTTP status."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _default_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        410: "GONE",
        413: "PAYLOAD_TOO_LARGE",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
    }.get(status_code, "HTTP_ERROR")


def _envelope(request: Request, code: str, message: str, status_code: int) -> dict[str, Any]:
    request_id = request.scope.get("request_id", "")
    return ErrorEnvelope(
        error=ErrorDetail(code=code, message=message, request_id=request_id)
    ).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, exc.code, exc.message, exc.status_code),
        )

    @app.exception_handler(VlmError)
    async def _handle_vlm_error(request: Request, exc: VlmError) -> Any:
        from fastapi.responses import JSONResponse

        status = VLM_ERROR_STATUS.get(exc.code, 502)
        return JSONResponse(
            status_code=status,
            content=_envelope(request, exc.code.value, exc.message, status),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> Any:
        from fastapi.responses import JSONResponse

        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, _default_code(exc.status_code), message, exc.status_code),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=422,
            content=_envelope(request, "VALIDATION_ERROR", "Request validation failed", 422),
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled(request: Request, exc: Exception) -> Any:
        from fastapi.responses import JSONResponse

        logger.exception("Unhandled application error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_envelope(request, "INTERNAL_ERROR", "Internal server error", 500),
        )
