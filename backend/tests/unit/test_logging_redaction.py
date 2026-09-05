"""Sensitive-data logging tests (M1 §21, §54).

Unit tests target the redaction utilities directly (deterministic and thread-safe). The request
logging middleware never logs header values by default; ``safe_headers`` is provided for any
future header logging.
"""

from __future__ import annotations

from app.core.logging import (
    redact_processor,
    redact_value,
    safe_headers,
)


def test_redact_value_marks_sensitive_keys() -> None:
    assert redact_value("authorization", "Bearer abc") == "[REDACTED]"
    assert redact_value("cookie", "session=abc") == "[REDACTED]"
    assert redact_value("set-cookie", "sid=abc") == "[REDACTED]"
    assert redact_value("api_key", "sk-123") == "[REDACTED]"
    assert redact_value("access_token", "tok") == "[REDACTED]"
    assert redact_value("password", "p@ss") == "[REDACTED]"
    assert redact_value("user-agent", "Chrome/120") == "Chrome/120"


def test_redact_value_is_case_insensitive() -> None:
    assert redact_value("Authorization", "Bearer abc") == "[REDACTED]"
    assert redact_value("COOKIE", "sid=1") == "[REDACTED]"


def test_redact_processor_redacts_sensitive_headers() -> None:
    event = {
        "event": "http.request",
        "authorization": "Bearer secret-token",
        "cookie": "session=abc",
        "path": "/health/live",
    }
    result = redact_processor(None, "info", event)
    assert result["authorization"] == "[REDACTED]"
    assert result["cookie"] == "[REDACTED]"
    assert result["path"] == "/health/live"


def test_redact_processor_redacts_nested_header_mapping() -> None:
    event = {
        "event": "http.request",
        "headers": {
            "Authorization": "Bearer secret-token",
            "User-Agent": "Chrome/120",
        },
    }
    result = redact_processor(None, "info", event)
    assert result["headers"]["Authorization"] == "[REDACTED]"
    assert result["headers"]["User-Agent"] == "Chrome/120"


def test_safe_headers_drops_sensitive_and_keeps_safe() -> None:
    headers = {
        "authorization": "Bearer secret-token",
        "cookie": "sid=abc",
        "set-cookie": "sid=def",
        "user-agent": "Chrome/120",
        "accept": "application/json",
    }
    safe = safe_headers(headers)
    assert "authorization" not in safe
    assert "cookie" not in safe
    assert "set-cookie" not in safe
    assert safe["user-agent"] == "Chrome/120"
    assert safe["accept"] == "application/json"


def test_no_sensitive_values_in_rendered_event() -> None:
    import json

    from structlog.processors import JSONRenderer

    event = {
        "event": "http.request",
        "authorization": "Bearer secret-token",
        "headers": {"Authorization": "Bearer secret-token"},
    }
    redacted = redact_processor(None, "info", event)
    rendered = JSONRenderer()(None, "info", redacted)
    payload = json.loads(rendered)
    assert "Bearer secret-token" not in json.dumps(payload)
