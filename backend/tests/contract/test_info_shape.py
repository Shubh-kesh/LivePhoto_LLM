"""Contract test: /api/v1/info response shape.

Guards the public response contract that the frontend Zod schema mirrors
(``frontend/src/schemas/info.ts``). No external contract platform is used in M1.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.factory import create_app
from tests.conftest import make_settings


def test_info_response_shape(client) -> None:
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"name", "version", "environment"}
    assert isinstance(body["name"], str)
    assert isinstance(body["version"], str)
    assert body["environment"] == "test"
    assert body["name"] == "LivePhoto"


def test_info_response_is_non_sensitive(settings) -> None:
    # The info endpoint must never expose configuration dumps, URLs or credentials.
    app = create_app(make_settings())
    with TestClient(app) as client:
        response = client.get("/api/v1/info")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"name", "version", "environment"}
    assert "database_url" not in response.text
    assert "cors" not in response.text.lower()
    assert "otel" not in response.text.lower()
    assert response.json() == {
        "name": "LivePhoto",
        "version": settings.app_version,
        "environment": "test",
    }
