"""Portrait-processing errors (M5.7 §44-47).

Failures are typed technical errors; the original image is never returned as a successful
processed portrait (no silent fallback, M5.7 §45).
"""

from __future__ import annotations

from enum import StrEnum


class PortraitErrorCode(StrEnum):
    PORTRAIT_PROCESSING_FAILED = "PORTRAIT_PROCESSING_FAILED"
    PORTRAIT_MODEL_UNAVAILABLE = "PORTRAIT_MODEL_UNAVAILABLE"
    PORTRAIT_MODEL_INTEGRITY = "PORTRAIT_MODEL_INTEGRITY"
    PORTRAIT_INVALID_SOURCE = "PORTRAIT_INVALID_SOURCE"
    #: The portrait matte is structurally unusable in the primary face/head region (severe
    #: fragmentation / missing face / strong asymmetry). Retryable quality failure — NOT liveness,
    #: spoof, fraud or multiple-faces. Fail closed; never promote a corrupted portrait.
    PORTRAIT_QUALITY_FAILED = "PORTRAIT_QUALITY_FAILED"


class PortraitProcessingError(Exception):
    def __init__(self, code: PortraitErrorCode, message: str | None = None) -> None:
        super().__init__(message or code.value)
        self.code = code
        self.message = message or code.value


#: Customer-safe RETRYABLE portrait-quality outcomes. These are expected image-quality results (the
#: backend worked; the matte is structurally unusable), NOT internal-server failures. They map to
#: HTTP 422 with a retry message and never mark the transaction as a technical error.
RETRYABLE_PORTRAIT_CODES: frozenset[PortraitErrorCode] = frozenset(
    {PortraitErrorCode.PORTRAIT_QUALITY_FAILED}
)


def portrait_error_status(code: PortraitErrorCode) -> int:
    return 422 if code in RETRYABLE_PORTRAIT_CODES else 500
