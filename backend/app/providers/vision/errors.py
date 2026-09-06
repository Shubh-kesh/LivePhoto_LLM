"""Provider-independent VLM error taxonomy (M4 §62-63).

Provider failures NEVER become LIVE (fail-closed). Distinct from capture-quality evidence and
camera errors.
"""

from __future__ import annotations

from enum import StrEnum

import httpx


class VlmErrorCode(StrEnum):
    VLM_DISABLED = "VLM_DISABLED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_AUTH_ERROR = "PROVIDER_AUTH_ERROR"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_BAD_REQUEST = "PROVIDER_BAD_REQUEST"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    TOO_MANY_IMAGES = "TOO_MANY_IMAGES"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    SCHEMA_VALIDATION_ERROR = "SCHEMA_VALIDATION_ERROR"
    PROVIDER_RESPONSE_ERROR = "PROVIDER_RESPONSE_ERROR"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


class VlmError(Exception):
    def __init__(self, code: VlmErrorCode, message: str | None = None) -> None:
        super().__init__(message or code.value)
        self.code = code
        self.message = message or code.value


#: HTTP statuses considered transient for retry purposes (M4 §31).
RETRYABLE_STATUS_CODES = frozenset({429, 408, 500, 502, 503, 504})


class VlmNotConfiguredError(VlmError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            VlmErrorCode.PROVIDER_NOT_CONFIGURED, f"provider '{provider}' is not configured"
        )


def map_provider_http_error(exc: Exception) -> VlmError:
    """Map transport/HTTP failures to the stable taxonomy (M4 §62)."""
    if isinstance(exc, httpx.TimeoutException):
        return VlmError(VlmErrorCode.PROVIDER_TIMEOUT, "provider request timed out")
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return VlmError(VlmErrorCode.PROVIDER_AUTH_ERROR, "provider authentication failed")
        if status == 429:
            return VlmError(VlmErrorCode.PROVIDER_RATE_LIMITED, "provider rate limited")
        if status in (408, 502, 503, 504) or status >= 500:
            return VlmError(VlmErrorCode.PROVIDER_UNAVAILABLE, "provider unavailable")
        if 400 <= status < 500:
            return VlmError(VlmErrorCode.PROVIDER_BAD_REQUEST, "provider rejected the request")
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return VlmError(VlmErrorCode.PROVIDER_UNAVAILABLE, "provider network error")
    if isinstance(exc, VlmError):
        return exc
    return VlmError(VlmErrorCode.UNKNOWN_PROVIDER_ERROR, str(exc))
