"""Outbound consumer callback (M5.8 §20-23).

Success-only callback carrying the processed JPEG as Base64 (encoded in memory, never persisted or
logged). The callback URL comes only from the trusted ConsumerProfile. Redirects are never followed
automatically. Retries are limited to transient failures with a stable Idempotency-Key.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import os
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.consumers import ConsumerProfile

CALLBACK_EVENT_TYPE = "LIVEPHOTO.DECISION.CREATED"
_IDEMPOTENCY_HEADER = "Idempotency-Key"


class CallbackTerminalError(Exception):
    """Callback failed in a deterministic, non-retryable way (4xx except 429, invalid response)."""

    def __init__(self, reason: str, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class CallbackTransportError(Exception):
    """Callback failed transiently (network/timeout/429/5xx) and may be retried."""


@dataclass(frozen=True)
class CallbackDelivery:
    acknowledged: bool
    status_code: int | None
    redirect_url: str | None
    latency_ms: int


def build_callback_event_id(consumer_id: str, external_transaction_id: str) -> str:
    """Stable idempotency key per consumer+external transaction+event (M5.8 §22)."""
    raw = f"{consumer_id}:{external_transaction_id}:{CALLBACK_EVENT_TYPE}".encode()
    return hashlib.sha256(raw).hexdigest()


def build_callback_payload(
    *,
    event_id: str,
    external_transaction_id: str,
    decision_id: str,
    processed_jpeg: bytes,
    occurred_at: str,
) -> dict[str, Any]:
    """Build the callback payload. Base64 exists only in this in-memory dict."""
    return {
        "event_id": event_id,
        "transaction_id": external_transaction_id,
        "decision_id": decision_id,
        "occurred_at": occurred_at,
        "processed_jpeg_base64": base64.b64encode(processed_jpeg).decode("ascii"),
        "processed_jpeg_sha256": hashlib.sha256(processed_jpeg).hexdigest(),
    }


def _resolve_bearer(profile: ConsumerProfile) -> str:
    secret = os.environ.get(profile.callback.secret_env, "")
    return secret


async def send_callback(
    settings: Settings,
    profile: ConsumerProfile,
    payload: dict[str, Any],
) -> CallbackDelivery:
    """Deliver a callback with transient-only retry and no redirect following."""
    timeout = settings.callback_timeout_seconds
    max_retries = settings.callback_max_retries
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        _IDEMPOTENCY_HEADER: str(payload["event_id"]),
    }
    if profile.callback.auth_type == "bearer_env":
        token = _resolve_bearer(profile)
        if not token:
            raise CallbackTransportError("callback bearer secret is not configured")
        headers["Authorization"] = f"Bearer {token}"

    import time

    attempt = 0
    last_error: Exception | None = None
    while True:
        attempt += 1
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.post(profile.callback.url, json=payload, headers=headers)
            latency = int((time.perf_counter() - started) * 1000)
        except httpx.HTTPError as exc:
            last_error = CallbackTransportError(f"callback network failure: {type(exc).__name__}")
            if attempt > max_retries:
                raise last_error from exc
            await _backoff(attempt)
            continue

        if response.status_code in (429,) or response.status_code >= 500:
            last_error = CallbackTransportError(f"callback transient HTTP {response.status_code}")
            if attempt > max_retries:
                raise last_error
            await _backoff(attempt)
            continue
        if response.status_code < 200 or response.status_code >= 300:
            raise CallbackTerminalError(
                f"callback refused with HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            body: Any = response.json()
        except ValueError as exc:
            raise CallbackTerminalError("callback returned non-JSON body") from exc
        redirect_url = body.get("redirect_url") if isinstance(body, dict) else None
        return CallbackDelivery(
            acknowledged=True,
            status_code=response.status_code,
            redirect_url=redirect_url if isinstance(redirect_url, str) else None,
            latency_ms=latency,
        )


async def _backoff(attempt: int) -> None:
    import asyncio

    await asyncio.sleep(min(0.2 * (2 ** (attempt - 1)), 2.0))


def validate_redirect_url(profile: ConsumerProfile, redirect_url: str, *, local: bool) -> bool:
    """Exact-origin redirect validation (M5.8 §23).

    Security requirement: exact allowed origin, HTTPS outside local, no userinfo, no
    javascript:/data: schemes. A query string is NOT an open-redirect vector and is allowed (e.g.
    ``https://consumer.example/path?code=abc``). Fragments are rejected (client-side only, could
    carry tokens in the URL hash). No substring matching / no endsWith domain logic.
    """
    if not redirect_url:
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(redirect_url)
    except ValueError:
        return False
    if parsed.username or parsed.password or parsed.fragment:
        return False
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        return False
    if parsed.hostname is None:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False  # out-of-range / non-numeric port -> validation failure, not an exception
    origin = parsed.scheme + "://" + parsed.hostname + (f":{port}" if port else "")
    return profile.allows_redirect_origin(origin)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()
