"""Shared provider helpers (M4 §30-32, §52-53, §77).

- Structured-output parsing: provider text -> strict VlmAssessment; invalid ->
  SCHEMA_VALIDATION_ERROR (never silently fixed).
- Conservative retries on transient failures only (429, selected 5xx, network reset/timeout).
  Authentication, bad request, unsupported inputs and schema errors caused by our request are NOT
  retried (M4 §31).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable

from app.providers.vision.errors import (
    VlmError,
    VlmErrorCode,
)
from app.providers.vision.models import VlmAssessment

RETRYABLE_CODES = {
    VlmErrorCode.PROVIDER_RATE_LIMITED,
    VlmErrorCode.PROVIDER_UNAVAILABLE,
    VlmErrorCode.PROVIDER_TIMEOUT,
}


def parse_assessment(text: str) -> VlmAssessment:
    """Parse and strictly validate provider output (M4 §52). Never guesses/fixes output."""
    try:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].lstrip()
            if stripped.endswith("```"):
                stripped = stripped[:-3].rstrip()
        data = json.loads(stripped)
        return VlmAssessment.model_validate(data)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise VlmError(
            VlmErrorCode.SCHEMA_VALIDATION_ERROR, "provider output did not match schema"
        ) from exc


def is_retryable_error(error: VlmError) -> bool:
    return error.code in RETRYABLE_CODES


async def run_with_retries[T](
    operation: Callable[[], Awaitable[T]],
    max_retries: int,
    *,
    retry_delay_seconds: float = 0.5,
) -> T:
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            return await operation()
        except VlmError as error:
            if attempt >= max_retries or not is_retryable_error(error):
                raise
            await asyncio.sleep(retry_delay_seconds * (2**attempt))
    raise VlmError(VlmErrorCode.PROVIDER_UNAVAILABLE, "provider retries exhausted")


def timing_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
