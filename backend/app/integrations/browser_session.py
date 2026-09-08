"""Browser session + launch redemption service (M5.8 §9-11).

A launch token redemption creates a separate opaque browser session. Only SHA-256 of the browser
session token and the CSRF token are persisted. The newest successful redemption invalidates the
previous active browser session for the same transaction.

Modes:
- ACTIVE: full capture/portrait/submit capability.
- TERMINAL: restricted session (e.g. COMPLETED) that may only bootstrap the safe terminal UI and
  must reject all mutations.
- INVALID / EXPIRED: no transaction/session is created (handled at the route via a launch-outcome
  cookie).
"""

from __future__ import annotations

import datetime
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.config import Settings
from app.integrations.store import IntegrationIndexStore, sha256_hex
from app.transactions.store import TransactionFileStore, TransactionStatus

SESSION_COOKIE = "lp_session"
CSRF_COOKIE = "lp_csrf"

_LAUNCH_OUTCOME_COOKIE = "lp_launch_outcome"

#: Transaction-relative path recording the current active browser-session token hash for a tx.
_ACTIVE_SESSION_PATH = "browser/active-session.json"


class RedemptionMode(StrEnum):
    ACTIVE = "ACTIVE"
    TERMINAL = "TERMINAL"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class RedemptionResult:
    mode: RedemptionMode
    internal_transaction_id: str | None
    session_token: str | None
    csrf_token: str | None
    terminal_state: str | None = None


def launch_outcome_cookie_name() -> str:
    return _LAUNCH_OUTCOME_COOKIE


def _new_opaque() -> str:
    return secrets.token_urlsafe(32)  # 256-bit


def is_terminal_status(status: str) -> bool:
    return status in (
        TransactionStatus.COMPLETED.value,
        TransactionStatus.ATTEMPT_LIMIT_EXCEEDED.value,
    )


def redeem_launch_token(
    settings: Settings,
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    raw_token: str,
) -> RedemptionResult:
    """Validate a launch token and create (or refuse) a browser session.

    The raw token is hashed immediately; it is never persisted or logged.
    """
    token_hash = sha256_hex(raw_token.encode("utf-8"))
    record = index_store.get_launch_token(token_hash)
    if record is None:
        return RedemptionResult(
            mode=RedemptionMode.INVALID,
            internal_transaction_id=None,
            session_token=None,
            csrf_token=None,
        )

    expires_at = record.get("expires_at", "")
    if _is_expired(expires_at):
        index_store.delete_launch_token(token_hash)
        return RedemptionResult(
            mode=RedemptionMode.EXPIRED,
            internal_transaction_id=None,
            session_token=None,
            csrf_token=None,
        )

    internal_tx_id = record.get("transaction_id")
    if not isinstance(internal_tx_id, str):
        return RedemptionResult(
            mode=RedemptionMode.INVALID,
            internal_transaction_id=None,
            session_token=None,
            csrf_token=None,
        )

    status = tx_store.read_transaction_json(internal_tx_id).get(
        "status", TransactionStatus.LAUNCHED.value
    )

    if is_terminal_status(status):
        return _create_session(
            settings,
            tx_store,
            index_store,
            internal_tx_id,
            mode=RedemptionMode.TERMINAL,
            terminal_state=status,
        )

    return _create_session(
        settings,
        tx_store,
        index_store,
        internal_tx_id,
        mode=RedemptionMode.ACTIVE,
        terminal_state=None,
    )


def _create_session(
    settings: Settings,
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    internal_tx_id: str,
    *,
    mode: RedemptionMode,
    terminal_state: str | None,
) -> RedemptionResult:
    session_token = _new_opaque()
    csrf_token = _new_opaque()
    session_hash = sha256_hex(session_token.encode("utf-8"))
    csrf_hash = sha256_hex(csrf_token.encode("utf-8"))
    now = datetime.datetime.now(datetime.UTC)
    expires = now + datetime.timedelta(seconds=settings.browser_session_ttl_seconds)

    with tx_store.lock_transaction(internal_tx_id):
        if mode == RedemptionMode.ACTIVE:
            _invalidate_previous_active(index_store, tx_store, internal_tx_id)
        index_store.put_browser_session(
            session_hash,
            {
                "transaction_id": internal_tx_id,
                "mode": mode.value,
                "terminal_state": terminal_state,
                "csrf_hash": csrf_hash,
                "created_at": now.isoformat(),
                "expires_at": expires.isoformat(),
                "revoked": False,
            },
        )
        if mode == RedemptionMode.ACTIVE:
            tx_store.write_json(
                internal_tx_id,
                _ACTIVE_SESSION_PATH,
                {
                    "session_hash": session_hash,
                    "created_at": now.isoformat(),
                    "expires_at": expires.isoformat(),
                },
            )

    return RedemptionResult(
        mode=mode,
        internal_transaction_id=internal_tx_id,
        session_token=session_token,
        csrf_token=csrf_token,
        terminal_state=terminal_state,
    )


def _invalidate_previous_active(
    index_store: IntegrationIndexStore, tx_store: TransactionFileStore, internal_tx_id: str
) -> None:
    if not tx_store.artifact_exists(internal_tx_id, _ACTIVE_SESSION_PATH):
        return
    try:
        data = tx_store.read_json(internal_tx_id, _ACTIVE_SESSION_PATH)
        prev_hash = data.get("session_hash")
        if isinstance(prev_hash, str):
            index_store.delete_browser_session(prev_hash)
    except Exception:
        return


def resolve_browser_session(
    settings: Settings,
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    session_token: str,
) -> dict[str, Any] | None:
    """Resolve a raw browser-session cookie to its index record, honoring TTL/revocation."""
    if not session_token:
        return None
    session_hash = sha256_hex(session_token.encode("utf-8"))
    record = index_store.get_browser_session(session_hash)
    if record is None:
        return None
    if record.get("revoked") is True:
        return None
    if _is_expired(record.get("expires_at", "")):
        index_store.delete_browser_session(session_hash)
        return None
    return record


def verify_csrf(
    settings: Settings, index_store: IntegrationIndexStore, record: dict[str, Any], csrf_token: str
) -> bool:
    """Constant-time compare of the presented CSRF token against the session-bound hash."""
    import hmac

    presented = sha256_hex((csrf_token or "").encode("utf-8"))
    stored = record.get("csrf_hash", "")
    if not isinstance(stored, str) or not stored:
        return False
    return hmac.compare_digest(presented, stored)


def _is_expired(expires_at: str) -> bool:
    try:
        expiry = datetime.datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return True
    return datetime.datetime.now(datetime.UTC) >= expiry
