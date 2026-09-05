"""Security header and CORS tests (M1 §44)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.factory import create_app
from tests.conftest import make_settings


def test_security_headers_present_on_api_response(client) -> None:
    response = client.get("/health/live")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_permissions_policy_keeps_camera_for_self(client) -> None:
    # M2 requires camera capture; the policy deliberately keeps camera=(self) and blocks others.
    response = client.get("/health/live")
    policy = response.headers["permissions-policy"]
    assert "camera=(self)" in policy
    assert "microphone=()" in policy


def test_docs_routes_exempt_from_strict_csp(client) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


def test_hsts_disabled_by_default(client) -> None:
    response = client.get("/health/live")
    assert "strict-transport-security" not in response.headers


def test_hsts_enabled_when_configured() -> None:
    app = create_app(make_settings(hsts_enabled=True))
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert "max-age=31536000" in response.headers["strict-transport-security"]


def test_cors_allows_configured_origin() -> None:
    app = create_app(make_settings(cors_origins=["http://localhost:5173"]))
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_rejects_unconfigured_origin() -> None:
    app = create_app(make_settings(cors_origins=["http://localhost:5173"]))
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers
