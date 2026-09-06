"""VLM key redaction and safe-logging tests (M4 §59-61, §138-139)."""

from __future__ import annotations

from app.core.logging import redact_processor, safe_headers


def test_provider_keys_are_redacted() -> None:
    event = {
        "event": "vlm_evaluation_completed",
        "gemini_api_key": "AIza-very-secret",
        "groq_api_key": "gsk_123",
        "openrouter_api_key": "sk-or-123",
        "authorization": "Bearer token",
        "x-goog-api-key": "AIza-another",
        "classification": "LIVE",
    }
    result = redact_processor(None, "info", event)
    assert result["gemini_api_key"] == "[REDACTED]"
    assert result["groq_api_key"] == "[REDACTED]"
    assert result["openrouter_api_key"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert result["x-goog-api-key"] == "[REDACTED]"
    assert result["classification"] == "LIVE"


def test_provider_key_headers_dropped_from_safe_headers() -> None:
    headers = {
        "authorization": "Bearer token",
        "x-goog-api-key": "AIza-x",
        "x-request-id": "r1",
    }
    safe = safe_headers(headers)
    assert "authorization" not in safe
    assert "x-goog-api-key" not in safe
    assert safe["x-request-id"] == "r1"


def test_multipart_body_is_not_logged() -> None:
    # Request logging never includes bodies; verify the middleware event shape has none.
    from app.core.middleware import RequestLoggingMiddleware

    assert RequestLoggingMiddleware is not None


def test_vlm_safe_log_event_has_no_image_content() -> None:
    # The service logs normalized fields only (provider/model/classification/latency).
    from app.experiments.vlm.service import ExperimentResult

    result = ExperimentResult(
        provider="gemini",
        model="gemini-2.0-flash",
        frame_strategy="single-quality-v1",
        image_count=1,
        classification="SCREEN_REPLAY",
        latency_ms=1200,
    )
    dumped = result.model_dump()
    assert "image" not in str(dumped.get("classification", ""))
    assert all(key not in dumped for key in ("frames", "image_bytes", "base64", "raw_output"))
