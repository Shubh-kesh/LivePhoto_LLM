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


class PortraitProcessingError(Exception):
    def __init__(self, code: PortraitErrorCode, message: str | None = None) -> None:
        super().__init__(message or code.value)
        self.code = code
        self.message = message or code.value
