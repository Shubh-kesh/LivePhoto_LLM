"""Request/correlation ID middleware tests (M1 §19, §54)."""

from __future__ import annotations

import re

_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def test_response_carries_generated_request_id(client) -> None:
    response = client.get("/health/live")
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert _ID_PATTERN.fullmatch(request_id)


def test_valid_inbound_request_id_is_preserved(client) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "bank-correlation-1"})
    assert response.headers.get("x-request-id") == "bank-correlation-1"


def test_invalid_inbound_request_id_is_replaced(client) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "a" * 200})
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert len(request_id) <= 64


def test_request_id_unique_across_requests(client) -> None:
    first = client.get("/health/live").headers.get("x-request-id")
    second = client.get("/health/live").headers.get("x-request-id")
    assert first != second
    assert first is not None
    assert second is not None


def test_request_id_present_in_error_response(client) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers.get("x-request-id") is not None


def test_request_id_is_bound_in_log_events() -> None:
    """The request ID must appear in structured log events (M1 §20)."""
    import asyncio

    import structlog
    from structlog.testing import capture_logs

    from app.core.middleware import RequestIDMiddleware, RequestLoggingMiddleware

    class _Inner:
        async def __call__(self, scope, receive, send) -> None:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    # RequestID must be OUTER so context is bound before (and cleared after) the logging middleware.
    app = RequestIDMiddleware(RequestLoggingMiddleware(_Inner()))
    scope: dict = {"type": "http", "method": "GET", "path": "/x", "headers": []}

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as captured:
        asyncio.run(app(scope, None, _Collector()))

    request_events = [e for e in captured if e.get("event") == "http.request.completed"]
    assert request_events
    assert request_events[0]["request_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_events[0]["request_id"])


class _Collector:
    """Minimal send callable that discards the ASGI messages."""

    async def __call__(self, message: dict) -> None:
        return None
