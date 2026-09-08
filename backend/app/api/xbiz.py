"""Browser launch redemption route (M5.8 §9, §23).

``GET /xbiz/live_photo/l/{opaque_token}`` — validates the opaque launch token and redirects to the
clean SPA URL ``/xbiz/live_photo/``. The raw token is hashed immediately and never logged or
persisted; the address bar is cleared by the 302.

- ACTIVE  -> set ``lp_session`` + ``lp_csrf`` cookies, 302 to clean URL.
- TERMINAL (e.g. COMPLETED) -> set cookies, 302 to clean URL; mutations later reject the session.
- INVALID/EXPIRED -> set a short-lived non-sensitive ``lp_launch_outcome`` cookie, 302 to clean URL.
"""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.core.config import Settings
from app.integrations.browser_session import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    RedemptionMode,
    launch_outcome_cookie_name,
    redeem_launch_token,
)
from app.integrations.store import IntegrationIndexStore
from app.transactions.store import TransactionFileStore

router = APIRouter(tags=["xbiz"])

CLEAN_URL = "/xbiz/live_photo/"
LAUNCH_OUTCOME_TTL_SECONDS = 60


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _store(request: Request) -> TransactionFileStore:
    return cast(TransactionFileStore, request.app.state.transaction_store)


def _index(request: Request) -> IntegrationIndexStore:
    return cast(IntegrationIndexStore, request.app.state.integration_index_store)


def _samesite(settings: Settings) -> Literal["strict", "lax", "none"]:
    return settings.browser_cookie_samesite


@router.get("/xbiz/live_photo/l/{opaque_token}")
def redeem(request: Request, opaque_token: str) -> RedirectResponse:
    settings = _settings(request)
    result = redeem_launch_token(_settings(request), _store(request), _index(request), opaque_token)
    response = RedirectResponse(CLEAN_URL, status_code=302)
    secure = settings.browser_cookie_secure
    samesite = _samesite(settings)

    if result.mode in (RedemptionMode.ACTIVE, RedemptionMode.TERMINAL):
        session_token = result.session_token or ""
        csrf_token = result.csrf_token or ""
        response.set_cookie(
            SESSION_COOKIE,
            session_token,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
            max_age=settings.browser_session_ttl_seconds,
        )
        response.set_cookie(
            CSRF_COOKIE,
            csrf_token,
            httponly=False,
            secure=secure,
            samesite=samesite,
            path="/",
            max_age=settings.browser_session_ttl_seconds,
        )
    else:
        # INVALID / EXPIRED: short-lived, non-sensitive outcome the SPA reads and clears.
        response.set_cookie(
            launch_outcome_cookie_name(),
            result.mode.value,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
            max_age=LAUNCH_OUTCOME_TTL_SECONDS,
        )
    return response
