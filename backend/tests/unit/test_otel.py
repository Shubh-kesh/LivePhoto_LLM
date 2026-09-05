"""OpenTelemetry foundation tests (M1 §47)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.factory import create_app
from tests.conftest import make_settings


def test_otel_disabled_by_default_does_not_affect_app(settings) -> None:
    assert settings.otel_enabled is False
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200


def test_otel_enabled_without_collector_starts_and_serves() -> None:
    # No OTLP collector configured in M1; console exporter optional. The app must start locally
    # regardless (no exporter may prevent startup).
    app = create_app(make_settings(otel_enabled=True, otel_traces_exporter="none"))
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200


def test_init_otel_returns_none_when_disabled() -> None:
    from app.observability.otel import init_otel

    tracer = init_otel(make_settings(otel_enabled=False))
    assert tracer is None
