"""Application factory tests (M1 §14-15, §54)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.factory import create_app
from tests.conftest import make_settings


def test_create_app_returns_configured_application(settings) -> None:
    app = create_app(settings)
    assert isinstance(app, FastAPI)
    assert app.title == settings.app_name
    assert app.version == settings.app_version


def test_app_boots_without_database(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200


def test_required_routes_respond(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/v1/info").status_code == 200
        assert client.get("/metrics").status_code == 200


def test_metrics_route_absent_when_disabled() -> None:
    app = create_app(make_settings(prometheus_enabled=False))
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 404
