"""Server-authoritative capture-attempt model (M5.8 §13-15).

One attempt = the user explicitly presses Capture. A frontend-generated opaque ``attempt_id`` is
registered at most once across the two server paths (``/browser/attempts`` quality-failure and
``/browser/capture`` upload). Browser-reported reasons are allowlisted preliminary quality signals
only; security/liveness outcomes are never browser-authored.
"""

from __future__ import annotations

import datetime
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.transactions.store import TransactionFileStore, TransactionStatus

ATTEMPTS_PATH = "attempts.json"

#: Preliminary quality reasons the browser may report. Mirror of the frontend QualityReasonCode
#: vocabulary (plus LOW_LIGHT). Anything outside this set is rejected.
BROWSER_REASON_ALLOWLIST: frozenset[str] = frozenset(
    {
        "NO_FACE",
        "MULTIPLE_FACES",
        "FACE_TOO_SMALL",
        "FACE_TOO_LARGE",
        "FACE_OFF_CENTER",
        "BLURRED",
        "UNDEREXPOSED",
        "OVEREXPOSED",
        "LOW_CONTRAST",
        "RESOLUTION_TOO_LOW",
        "EYES_CLOSED",
        "EYE_STATE_UNKNOWN",
        "LOW_LIGHT",
    }
)

#: Outcome/reason values the browser must never report authoritatively (M5.8 §14).
FORBIDDEN_BROWSER_VALUES: frozenset[str] = frozenset(
    {"PASS", "LIVE", "APPROVED", "VERIFIED", "SCREEN_REPLAY", "PRINT_ATTACK"}
)

ALLOWED_BROWSER_RESULTS: frozenset[str] = frozenset({"QUALITY_RETRY"})


class AttemptValidationError(Exception):
    """A browser-reported attempt value is disallowed/unknown (controlled validation error)."""


@dataclass(frozen=True)
class AttemptResult:
    attempt_count: int
    max_attempts: int
    warning: bool
    terminal: bool
    status: str | None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _attempt_id_hash(attempt_id: str) -> str:
    return hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()


def validate_reason(reason_code: str | None) -> None:
    """Validate a browser-reported reason; reject forbidden/unknown values."""
    if reason_code is None:
        return
    if reason_code in FORBIDDEN_BROWSER_VALUES or reason_code not in BROWSER_REASON_ALLOWLIST:
        raise AttemptValidationError(f"disallowed reason code: {reason_code}")


def validate_result(result: str | None) -> None:
    if result is not None and result not in ALLOWED_BROWSER_RESULTS:
        raise AttemptValidationError(f"disallowed attempt result: {result}")


def _blank_attempts(max_attempts: int) -> dict[str, Any]:
    return {
        "attempt_count": 0,
        "warning_stages": [5, 7],
        "limit": max_attempts,
        "consumed_attempt_ids": [],
        "reason_codes": [],
        "updated_at": _now_iso(),
    }


def _read_attempts(
    tx_store: TransactionFileStore, internal_tx_id: str, max_attempts: int
) -> dict[str, Any]:
    if not tx_store.artifact_exists(internal_tx_id, ATTEMPTS_PATH):
        return _blank_attempts(max_attempts)
    try:
        data = tx_store.read_json(internal_tx_id, ATTEMPTS_PATH)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _blank_attempts(max_attempts)


def register_attempt(
    settings: Settings,
    tx_store: TransactionFileStore,
    internal_tx_id: str,
    *,
    attempt_id: str,
    result: str | None,
    reason_code: str | None,
    max_attempts: int | None = None,
) -> AttemptResult:
    """Register a capture attempt at most once under the per-transaction lock (M5.8 §13, §15).

    The effective limit is the consumer-profile ``max_attempts`` when provided, else the global
    ``CAPTURE_ATTEMPT_LIMIT``. Warning stages always come from server settings.
    """
    validate_result(result)
    validate_reason(reason_code)
    effective_limit = (
        max_attempts if max_attempts and max_attempts > 0 else settings.capture_attempt_limit
    )
    id_hash = _attempt_id_hash(attempt_id)
    terminal = False
    warning = False

    with tx_store.lock_transaction(internal_tx_id):
        attempts = _read_attempts(tx_store, internal_tx_id, effective_limit)
        consumed = attempts.get("consumed_attempt_ids", [])
        if not isinstance(consumed, list):
            consumed = []
        if id_hash not in consumed:
            consumed.append(id_hash)
            attempts["consumed_attempt_ids"] = consumed
            attempts["attempt_count"] = int(attempts.get("attempt_count", 0)) + 1
            if reason_code:
                codes = attempts.get("reason_codes", [])
                if not isinstance(codes, list):
                    codes = []
                if reason_code not in codes:
                    codes.append(reason_code)
                attempts["reason_codes"] = codes
            attempts["updated_at"] = _now_iso()
        # Server-authoritative warning/limit stages come from settings, not stored defaults.
        attempts["warning_stages"] = [
            settings.capture_attempt_warning_at,
            settings.capture_attempt_warning_again_at,
        ]
        attempts["limit"] = effective_limit

        count = int(attempts.get("attempt_count", 0))
        warning_stages = attempts["warning_stages"]
        if count in warning_stages:
            warning = True

        if count >= effective_limit:
            terminal = True
            tx_store.update_transaction_status(
                internal_tx_id, TransactionStatus.ATTEMPT_LIMIT_EXCEEDED.value
            )

        tx_store.write_json(internal_tx_id, ATTEMPTS_PATH, attempts)

    return AttemptResult(
        attempt_count=count,
        max_attempts=effective_limit,
        warning=warning,
        terminal=terminal,
        status=TransactionStatus.ATTEMPT_LIMIT_EXCEEDED.value if terminal else None,
    )


def read_attempt_summary(
    tx_store: TransactionFileStore, internal_tx_id: str, max_attempts: int
) -> dict[str, Any]:
    attempts = _read_attempts(tx_store, internal_tx_id, max_attempts)
    return {
        "attempt_count": int(attempts.get("attempt_count", 0)),
        "max_attempts": max_attempts,
        "reason_codes": list(attempts.get("reason_codes", [])),
    }


def new_attempt_id() -> str:
    return uuid.uuid4().hex
