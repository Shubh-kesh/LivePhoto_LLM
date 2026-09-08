"""FastAPI dependencies and typed browser-session auth errors (M5.8 §10-12)."""

from __future__ import annotations

from typing import Any, cast

from fastapi import Request

from app.core.config import Settings
from app.integrations.browser_session import (
    RedemptionMode,
    resolve_browser_session,
    verify_csrf,
)
from app.integrations.store import IntegrationIndexStore
from app.transactions.store import TransactionFileStore


class BrowserAuthError(Exception):
    """Browser-session / CSRF authentication failure."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _store(request: Request) -> TransactionFileStore:
    return cast(TransactionFileStore, request.app.state.transaction_store)


def _index(request: Request) -> IntegrationIndexStore:
    return cast(IntegrationIndexStore, request.app.state.integration_index_store)


def resolve_session_record(request: Request) -> dict[str, Any] | None:
    """Resolve the browser session record from the ``lp_session`` cookie (or None)."""
    session_token = request.cookies.get("lp_session", "")
    return resolve_browser_session(
        _settings(request), _store(request), _index(request), session_token
    )


def require_active_session(request: Request) -> dict[str, Any]:
    """Require a non-terminal (ACTIVE) browser session; used by all mutations."""
    record = resolve_session_record(request)
    if record is None:
        raise BrowserAuthError(
            code="SESSION_INVALID", message="No active browser session", status_code=401
        )
    if record.get("mode") != RedemptionMode.ACTIVE.value:
        raise BrowserAuthError(
            code="SESSION_TERMINAL", message="Session is in a terminal state", status_code=409
        )
    return record


def require_csrf(request: Request, record: dict[str, Any]) -> None:
    """Validate the session-bound CSRF token (M5.8 §11)."""
    token = request.headers.get("X-CSRF-Token", "")
    if not verify_csrf(_settings(request), _index(request), record, token):
        raise BrowserAuthError(
            code="CSRF_INVALID", message="CSRF validation failed", status_code=403
        )
