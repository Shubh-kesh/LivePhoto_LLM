"""Prometheus foundation tests (M1 §45-46, §54)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.factory import create_app
from tests.conftest import make_settings


def test_metrics_endpoint_exposes_core_metrics(client) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "livephoto_http_requests_total" in body
    assert "livephoto_http_request_duration_seconds" in body


def test_metrics_contains_no_high_cardinality_labels() -> None:
    from app.observability.metrics import http_request_duration_seconds

    assert tuple(http_request_duration_seconds._labelnames) == ("method", "path")


def test_metrics_404_when_disabled() -> None:
    app = create_app(make_settings(prometheus_enabled=False))
    with TestClient(app) as client:
        response = client.get("/metrics")
    assert response.status_code == 404


def test_metric_recording_helper() -> None:
    from app.observability.metrics import record_http_request

    record_http_request(method="GET", route_path="/health/live", status=200, duration_seconds=0.01)
    record_http_request(method="GET", route_path=None, status=404, duration_seconds=0.01)
    # Labels never contain IDs; the helper must accept only low-cardinality inputs.
    record_http_request(
        method="POST", route_path="/api/v1/sessions", status=201, duration_seconds=0.02
    )
