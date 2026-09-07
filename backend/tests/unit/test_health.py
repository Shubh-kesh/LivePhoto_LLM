"""Health endpoint tests (M1 §16, §54)."""

from __future__ import annotations

from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app.core.health import ReadinessResult, database_readiness_check
from app.factory import create_app


def test_health_live_ok(client) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_ok_without_database(client) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    names = [check["name"] for check in body["checks"]]
    assert "file_storage" in names
    storage = next(check for check in body["checks"] if check["name"] == "file_storage")
    assert storage["status"] == "ok"


class _BoomEngine:
    """Engine stub whose connect always fails (no network, no DBAPI)."""

    def connect(self) -> None:
        raise RuntimeError("boom")


def test_database_readiness_check_ok() -> None:
    # SQLite is used here only to exercise the probe deterministically; it is NOT
    # production-equivalent (production is MSSQL, see docs/NON_FUNCTIONAL_REQUIREMENTS.md).
    engine = create_engine("sqlite:///:memory:")
    assert database_readiness_check(engine).status == "ok"


def test_database_readiness_check_unavailable() -> None:
    result = database_readiness_check(cast(Engine, _BoomEngine()))
    assert result.status == "unavailable"
    assert result.detail == "database unreachable"


def test_health_ready_returns_503_when_dependency_unavailable(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.ready_checks.append(
            lambda: ReadinessResult(
                name="database", status="unavailable", detail="database unreachable"
            )
        )
        response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    database_check = next((check for check in body["checks"] if check["name"] == "database"), None)
    assert database_check is not None
    assert database_check["status"] == "unavailable"


def test_health_live_succeeds_even_when_dependency_down(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.ready_checks.append(
            lambda: ReadinessResult(
                name="database", status="unavailable", detail="database unreachable"
            )
        )
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
