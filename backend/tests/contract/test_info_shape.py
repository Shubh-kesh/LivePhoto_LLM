"""Contract test: /api/v1/info response shape.

Guards the public response contract that the frontend Zod schema mirrors
(``frontend/src/schemas/info.ts``). No external contract platform is used in M1.

The response exposes name/version/environment plus the safe browser-support policy
(``browser_policy``), which may be null when the policy is not configured (explicit absence).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.factory import create_app
from tests.conftest import make_settings


def test_info_response_shape(client) -> None:
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"name", "version", "environment", "browser_policy"}
    assert isinstance(body["name"], str)
    assert isinstance(body["version"], str)
    assert body["environment"] == "test"
    assert body["name"] == "LivePhoto"
    # The committed policy is valid in the test environment, so it is present and well-formed.
    policy = body["browser_policy"]
    assert policy is not None
    assert policy["policy_version"]
    assert set(policy["browsers"].keys()) == {
        "chrome",
        "edge",
        "firefox",
        "safari",
        "ios_safari",
        "android_chrome",
    }
    for entry in policy["browsers"].values():
        assert isinstance(entry["minimum_major"], int) and entry["minimum_major"] > 0
        assert isinstance(entry["enabled"], bool)


def test_info_response_is_non_sensitive(settings) -> None:
    # The info endpoint must never expose configuration dumps, URLs or credentials.
    app = create_app(make_settings())
    with TestClient(app) as client:
        response = client.get("/api/v1/info")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"name", "version", "environment", "browser_policy"}
    assert "database_url" not in response.text
    assert "cors" not in response.text.lower()
    assert "otel" not in response.text.lower()
    assert "browser-support.json" not in response.text
    assert "config" not in response.text.lower()
    assert "secret" not in response.text.lower()
    assert body["name"] == "LivePhoto"
    assert body["version"] == settings.app_version
    assert body["environment"] == "test"
