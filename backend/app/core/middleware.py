"""HTTP middleware: request IDs, request logging, security headers.

Pure-ASGI middlewares (no BaseHTTPMiddleware) so headers/context are applied even when an inner
handler raises; exception handlers sit outside these middlewares and still receive them.
"""

from __future__ import annotations

import re
import secrets
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.logging import bind_request_context, clear_request_context, get_logger
from app.observability.metrics import record_http_request

#: Accepted inbound X-Request-ID shape (bounded length, no PII, no control characters).
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_REQUEST_ID_HEADER = "x-request-id"

_CSP = "default-src 'none'; frame-ancestors 'none'"
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

#: Launch redemption prefix that carries an opaque token in the URL. When the matched route
#: template is unavailable we must still never log the raw token segment (M5.8 §24).
_LAUNCH_REDEMPTION_PREFIX = "/xbiz/live_photo/l/"
_LAUNCH_REDEMPTION_TEMPLATE = "/xbiz/live_photo/l/{token}"


def _safe_request_path(scope: Scope) -> str:
    """Return a log-safe request path.

    Prefer the matched route template (like MetricsMiddleware); otherwise fall back to the raw path
    with the launch-redemption token replaced by ``{token}``. Query strings are never included
    (ASGI ``scope["path"]`` excludes the query string).
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    path = scope.get("path", "") or ""
    if path.startswith(_LAUNCH_REDEMPTION_PREFIX):
        return _LAUNCH_REDEMPTION_TEMPLATE
    return path


class RequestIDMiddleware:
    """Generate/accept a request ID, expose it on the response and bind it to logging context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        incoming = _header_value(headers, _REQUEST_ID_HEADER)
        request_id = (
            incoming if incoming and _REQUEST_ID_PATTERN.fullmatch(incoming) else _new_request_id()
        )
        scope["request_id"] = request_id
        scope.setdefault("state", {})["request_id"] = request_id
        bind_request_context(
            request_id=request_id,
            method=scope.get("method", ""),
            path=_safe_request_path(scope),
        )

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = message.get("headers", [])
                message["headers"] = [
                    *response_headers,
                    (b"x-request-id", request_id.encode("ascii")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_request_context()


class RequestLoggingMiddleware:
    """Log one structured event per completed HTTP request (never header values)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = get_logger("livephoto.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._logger.info(
                "http.request.completed",
                status_code=status if status is not None else 500,
                duration_ms=duration_ms,
                method=scope.get("method", ""),
                path=_safe_request_path(scope),
            )


class SecurityHeadersMiddleware:
    """Apply security headers to every HTTP response.

    The strict CSP applies only to non-documentation routes so Swagger/ReDoc keep working in
    local development. Camera remains permitted for the same origin (``camera=(self)``) so the M2
    capture feature is not blocked; the policy is validated again during M2.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.hsts_enabled = settings.hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        csp = None if path in _DOCS_PATHS else _CSP

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                additions = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                    (
                        b"permissions-policy",
                        b"camera=(self), microphone=(), geolocation=(), payment=(), usb=()",
                    ),
                ]
                if csp is not None:
                    additions.append((b"content-security-policy", csp.encode("ascii")))
                if self.hsts_enabled:
                    additions.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = [*headers, *additions]
            await send(message)

        await self.app(scope, receive, send_wrapper)


class MetricsMiddleware:
    """Record Prometheus HTTP metrics (only installed when Prometheus is enabled).

    Labels use the matched route template (or ``unmatched``) plus method and status — never IDs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status: int | None = None
        route_path: str | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status, route_path
            if message["type"] == "http.response.start":
                status = int(message.get("status", 500))
                route = scope.get("route")
                route_path = getattr(route, "path", None) or "unmatched"
            await send(message)

        await self.app(scope, receive, send_wrapper)
        record_http_request(
            method=scope.get("method", ""),
            route_path=route_path,
            status=status if status is not None else 500,
            duration_seconds=time.perf_counter() - start,
        )


def _new_request_id() -> str:
    return secrets.token_hex(16)


def _header_value(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    target = name.encode("ascii")
    for key, value in headers:
        if key.lower() == target:
            return value.decode("latin-1")
    return None
