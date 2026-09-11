"""M5.8 Secure Consumer Integration tests."""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import http.server
import io
import json
import os
import threading
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.domain.decision import DecisionOutcome
from app.experiments.vlm import liveness
from app.factory import create_app
from app.integrations.callback import build_callback_event_id
from app.integrations.store import external_key_hash
from app.transactions.ids import INTERNAL_TRANSACTION_ID_PATTERN
from app.transactions.store import TransactionFileStore

#: Valid primary normalized face box used across capture/portrait tests (geometry guidance only).
_FACE_BOX = "0.35,0.28,0.30,0.26"

D365 = {
    "consumer_id": "D365",
    "active": True,
    "name": "Test D365",
    "jwt_client_ids": ["d365-livephoto-client"],
    "callback": {
        "url": "http://localhost:0/livephoto/callback",
        "auth_type": "none",
        "secret_env": "D365_CALLBACK_BEARER_TOKEN",
    },
    "allowed_redirect_origins": ["http://localhost:3001"],
    "request_policy": {
        "ocr_required": [False],
        "camera_configs": ["1"],
        "white_background": [True],
        "output_formats": ["jpeg"],
    },
    "max_attempts": 10,
}


def _jpeg_bytes(width: int = 96, height: int = 128) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (110, 130, 150)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _write_consumers(tmp_path, entries: list[dict[str, Any]]) -> str:
    path = tmp_path / "consumers.json"
    path.write_text(json.dumps({"consumers": entries}))
    return str(path)


def _make_app(tmp_path, *, consumers: list[dict[str, Any]] | None = None, **overrides: object):
    settings_kwargs: dict[str, object] = {
        "app_env": "test",
        "file_storage_root": str(tmp_path / "storage"),
        "consumer_profiles_path": _write_consumers(
            tmp_path, consumers if consumers is not None else [D365]
        ),
        "s2s_auth_mode": "local_dev",
        "s2s_local_dev_token": "dev-secret",
        "public_livephoto_base_url": "http://localhost:5173",
        "portrait_processing_enabled": True,
        "portrait_background_color": "#FFFFFF",
        "portrait_segmentation_provider": "fake",
        "decision_test_writer_enabled": True,
        "vlm_experiment_enabled": True,
        "callback_timeout_seconds": 2.0,
        "callback_max_retries": 2,
        "browser_cookie_secure": False,
    }
    settings_kwargs.update(overrides)
    settings = Settings(_env_file=None, **settings_kwargs)  # type: ignore[arg-type]
    app = create_app(settings)
    from app.portrait import FakePortraitSegmentation

    app.state.portrait_segmentation = FakePortraitSegmentation()
    return app


def _dev_headers() -> dict[str, str]:
    return {"X-LivePhoto-Dev-Auth": "dev-secret"}


def _launch(
    client: TestClient, *, source: str = "D365", body: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = {"transaction_id": "ext-123", "source": source}
    if body:
        payload.update(body)
    response = client.post(
        "/api/v1/integration/launch-sessions", json=payload, headers=_dev_headers()
    )
    assert response.status_code == 200, response.text
    return response.json()


def _launch_url_token(launch_url: str) -> str:
    return launch_url.rsplit("/", 1)[-1]


def _redeem(client: TestClient, token: str):
    return client.get(f"/xbiz/live_photo/l/{token}", follow_redirects=False)


def _cookies_from_response(response) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        pair = header.split(";", 1)[0]
        if "=" in pair:
            name, value = pair.split("=", 1)
            cookies[name] = value
    return cookies


def _browser_headers(session_cookie: str, csrf: str) -> dict[str, str]:
    return {"Cookie": f"lp_session={session_cookie}", "X-CSRF-Token": csrf}


def _live_portrait(client: TestClient, cookies: dict[str, str]):
    """Capture is already uploaded: run authoritative liveness (LIVE) then generate the portrait."""
    bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
    lv = client.post("/api/v1/browser/liveness", headers=bh)
    assert lv.status_code == 200, lv.text
    assert lv.json()["portrait_allowed"] is True
    portrait = client.post("/api/v1/browser/portrait", headers=bh)
    assert portrait.status_code == 200, portrait.text
    return bh


# ------------------------------------------------------------------ S2S auth
def test_local_dev_create_launch(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
        assert body["transaction_id"] == "ext-123"
        assert body["launch_url"].startswith("http://localhost:5173/xbiz/live_photo/l/")
        assert body["expires_in_seconds"] == 600
        assert (
            "Cache-Control"
            in client.post(
                "/api/v1/integration/launch-sessions",
                json={"transaction_id": "ext-2", "source": "D365"},
                headers=_dev_headers(),
            ).headers
        )


def test_local_dev_bad_credentials(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-1", "source": "D365"},
            headers={"X-LivePhoto-Dev-Auth": "wrong"},
        )
        assert response.status_code == 401


def test_local_dev_blocked_in_uat(tmp_path) -> None:
    with pytest.raises(ValueError):
        _make_app(tmp_path, app_env="uat", s2s_auth_mode="local_dev")


def test_source_mismatch_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-1", "source": "OTHER"},
            headers=_dev_headers(),
        )
        assert response.status_code == 403


def test_inactive_consumer_refused(tmp_path) -> None:
    profile = dict(D365, active=False)
    app = _make_app(tmp_path, consumers=[profile])
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-1", "source": "D365"},
            headers=_dev_headers(),
        )
        assert response.status_code == 403


def test_request_policy_denied(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-1", "source": "D365", "white_background": False},
            headers=_dev_headers(),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "REQUEST_POLICY_VIOLATION"


def test_extra_field_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-1", "source": "D365", "legacy_token": "x", "hash": "y"},
            headers=_dev_headers(),
        )
        assert response.status_code == 422


# ------------------------------------------------------------- JWT auth
def _make_jwks() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_numbers = key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "test-key-1",
                "n": _b64u(public_numbers.n),
                "e": _b64u(public_numbers.e),
            }
        ]
    }
    return private_pem, json.dumps(jwks)


def _b64u(value: int) -> str:

    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


def _make_token(private_pem: str, **claims: Any) -> str:
    payload = {
        "iss": "https://issuer.test",
        "aud": "livephoto",
        "exp": 4_999_999_999,
        "client_id": "d365-livephoto-client",
    }
    payload.update(claims)
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "test-key-1"})


def _make_jwt_app(tmp_path, jwks: str, **overrides: object):
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(jwks)
    return _make_app(
        tmp_path,
        s2s_auth_mode="jwt",
        s2s_jwt_issuer="https://issuer.test",
        s2s_jwt_audience="livephoto",
        s2s_jwt_jwks_url=str(jwks_path),
        s2s_jwt_client_id_claim="client_id",
        s2s_jwt_clock_skew_seconds=30,
        **overrides,
    )


def test_jwt_valid(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(private_pem)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text


def test_jwt_bad_signature(tmp_path) -> None:
    _private_pem, jwks = _make_jwks()
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(other_pem)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


def test_jwt_wrong_issuer(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(private_pem, iss="https://wrong.test")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


def test_jwt_wrong_audience(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(private_pem, aud="other")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


def test_jwt_expired(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(private_pem, exp=1)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


def test_jwt_nbf_future(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(private_pem, nbf=5_000_000_000)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


def test_jwt_missing_identity_claim(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = jwt.encode(
        {"iss": "https://issuer.test", "aud": "livephoto", "exp": 4_999_999_999},
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


def test_jwt_unknown_client_id(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(private_pem, client_id="unknown-client")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "D365"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


def test_jwt_source_mismatch(tmp_path) -> None:
    private_pem, jwks = _make_jwks()
    app = _make_jwt_app(tmp_path, jwks)
    token = _make_token(private_pem)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-j", "source": "OTHER"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ------------------------------------------------------------ launch token
def test_launch_token_entropy_and_hash_only(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
    token = _launch_url_token(body["launch_url"])
    assert len(token) >= 43  # token_urlsafe(32) length
    index = app.state.integration_index_store
    # raw token must not be persisted anywhere
    assert index.get_launch_token(token) is None
    from app.integrations.store import sha256_hex

    assert index.get_launch_token(sha256_hex(token.encode())) is not None


def test_launch_duplicate_external_409(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _launch(client)
        response = client.post(
            "/api/v1/integration/launch-sessions",
            json={"transaction_id": "ext-123", "source": "D365"},
            headers=_dev_headers(),
        )
        assert response.status_code == 409


def test_reissue_preserves_transaction_and_revokes_old(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        first = _launch(client)
        first_token = _launch_url_token(first["launch_url"])
        response = client.post(
            "/api/v1/integration/transactions/ext-123/launch-sessions?source=D365",
            headers=_dev_headers(),
        )
        assert response.status_code == 200, response.text
        second_token = _launch_url_token(response.json()["launch_url"])
        assert first_token != second_token
        # old token revoked -> invalid redemption
        assert _redeem(client, first_token).status_code == 302
        index = app.state.integration_index_store
        from app.integrations.store import sha256_hex

        assert index.get_launch_token(sha256_hex(first_token.encode())) is None
        assert index.get_launch_token(sha256_hex(second_token.encode())) is not None


def test_external_id_never_used_as_path(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _launch(client)
    index_root = app.state.integration_index_store.root
    # no file named after the external id anywhere under storage
    for _root, _dirs, files in os.walk(index_root):
        for name in files:
            assert "ext-123" not in name
    store: TransactionFileStore = app.state.transaction_store
    # internal tx folder name is the UUID hex, not external
    from app.transactions.store import is_valid_transaction_id

    for child in (store.root / "transactions").iterdir():
        assert is_valid_transaction_id(child.name)


# ------------------------------------------------------------- redemption
def test_redemption_active_sets_cookies_clean_url(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
        token = _launch_url_token(body["launch_url"])
        response = _redeem(client, token)
        assert response.status_code == 302
        assert response.headers["location"] == "/xbiz/live_photo/"
        cookies = _cookies_from_response(response)
        assert "lp_session" in cookies
        assert "lp_csrf" in cookies


def test_redemption_invalid_sets_outcome_cookie(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        response = _redeem(client, "not-a-real-token")
        assert response.status_code == 302
        assert response.headers["location"] == "/xbiz/live_photo/"
        cookies = _cookies_from_response(response)
        assert "lp_session" not in cookies
        assert cookies.get("lp_launch_outcome") == "INVALID"


def test_browser_session_state_invalid(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/browser/session")
        assert response.status_code == 200
        assert response.json()["state"] == "invalid"


def test_browser_session_active_and_csrf(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
        response = _redeem(client, _launch_url_token(body["launch_url"]))
        cookies = _cookies_from_response(response)
        state = client.get(
            "/api/v1/browser/session", headers={"Cookie": f"lp_session={cookies['lp_session']}"}
        )
        assert state.json()["state"] == "active"
        assert state.json()["submission_ready"] is False


def test_csrf_missing_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
        response = _redeem(client, _launch_url_token(body["launch_url"]))
        cookies = _cookies_from_response(response)
        # no csrf header
        res = client.post(
            "/api/v1/browser/attempts",
            data={"attempt_id": "a1", "result": "QUALITY_RETRY", "reason_code": "EYES_CLOSED"},
            headers={"Cookie": f"lp_session={cookies['lp_session']}"},
        )
        assert res.status_code == 403


def test_second_redemption_invalidates_first_session(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
        token = _launch_url_token(body["launch_url"])
        first = _cookies_from_response(_redeem(client, token))
        second = _cookies_from_response(_redeem(client, token))
        assert first["lp_session"] != second["lp_session"]
        # first session now invalid
        state = client.get(
            "/api/v1/browser/session", headers={"Cookie": f"lp_session={first['lp_session']}"}
        )
        assert state.json()["state"] == "invalid"


# -------------------------------------------------------------- attempts
def _active_cookies(client: TestClient) -> dict[str, str]:
    body = _launch(client)
    return _cookies_from_response(_redeem(client, _launch_url_token(body["launch_url"])))


def _attempts(
    client: TestClient, cookies: dict[str, str], attempt_id: str, reason: str = "EYES_CLOSED"
):
    return client.post(
        "/api/v1/browser/attempts",
        data={"attempt_id": attempt_id, "result": "QUALITY_RETRY", "reason_code": reason},
        headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
    )


def test_quality_failure_counts(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _attempts(client, cookies, "a1", "EYES_CLOSED")
        assert res.status_code == 200
        assert res.json()["attempt_count"] == 1


def test_browser_pass_reason_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _attempts(client, cookies, "a1", "PASS")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "DISALLOWED_REASON"
        res = _attempts(client, cookies, "a2", "SCREEN_REPLAY")
        assert res.status_code == 400


def test_attempt_id_at_most_once(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _attempts(client, cookies, "a1", "EYES_CLOSED")
        _attempts(client, cookies, "a1", "EYES_CLOSED")
        state = client.get(
            "/api/v1/browser/session", headers={"Cookie": f"lp_session={cookies['lp_session']}"}
        )
        assert state.json()["attempt_count"] == 1


def test_attempt_warning_and_limit(tmp_path) -> None:
    profile = dict(D365, max_attempts=4)
    app = _make_app(
        tmp_path,
        consumers=[profile],
        capture_attempt_warning_at=2,
        capture_attempt_warning_again_at=3,
        capture_attempt_limit=4,
    )
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        assert _attempts(client, cookies, "a1", "BLURRED").json()["warning"] is False
        assert _attempts(client, cookies, "a2", "BLURRED").json()["warning"] is True
        assert _attempts(client, cookies, "a3", "BLURRED").json()["warning"] is True
        res = _attempts(client, cookies, "a4", "BLURRED")
        assert res.status_code == 200
        assert res.json()["terminal"] is True
        # further attempts blocked
        res = _attempts(client, cookies, "a5", "BLURRED")
        assert res.status_code == 409


def test_capture_upload_counts_and_attempt_id_dedup(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _attempts(client, cookies, "c1", "EYES_CLOSED")
        # same attempt_id on capture -> no double count
        res = client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "c1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
        )
        assert res.status_code == 200
        assert res.json()["attempt_count"] == 1


# --------------------------------------------------------------- status API
def test_status_api(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _attempts(client, _active_cookies(client), "a1", "EYES_CLOSED")
        res = client.get(
            "/api/v1/integration/transactions/ext-123/status?source=D365", headers=_dev_headers()
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "RETRY_REQUIRED"
        assert body["attempt_count"] == 1
        assert body["max_attempts"] == 10
        assert body["reason_codes"] == ["EYES_CLOSED"]
        assert "processed_jpeg_base64" not in json.dumps(body)
        assert "internal_transaction_id" not in json.dumps(body)


def test_status_cross_consumer_404(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _launch(client)
        res = client.get(
            "/api/v1/integration/transactions/ext-123/status?source=OTHER", headers=_dev_headers()
        )
        assert res.status_code in (403, 404)


def test_status_unknown_404(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/integration/transactions/nope/status?source=D365", headers=_dev_headers()
        )
        assert res.status_code == 404


# ----------------------------------------------------- decision + submit
def _redeem_and_capture(client: TestClient) -> dict[str, str]:
    cookies = _active_cookies(client)
    res = client.post(
        "/api/v1/browser/capture",
        data={"attempt_id": "cap1", "face_box": _FACE_BOX},
        files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
        headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
    )
    assert res.status_code == 200
    return cookies


def test_submit_blocked_without_decision(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _redeem_and_capture(client)
        res = client.post(
            "/api/v1/browser/submit",
            headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
        )
        assert res.status_code == 412
        assert res.json()["error"]["code"] == "NOT_READY"


def test_decision_writer_absent_in_uat(tmp_path) -> None:
    app = _make_app(
        tmp_path,
        app_env="uat",
        s2s_auth_mode="jwt",
        s2s_jwt_jwks_url="http://issuer.test/jwks",
        browser_cookie_secure=True,
        public_livephoto_base_url="https://livephoto.example",
    )
    with TestClient(app) as client:
        assert client.post("/api/v1/dev/test-decision").status_code == 404


def test_full_submit_flow(tmp_path) -> None:
    # local callback server
    received: dict[str, Any] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            received["body"] = self.rfile.read(length)
            received["headers"] = dict(self.headers)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = dict(
            D365,
            **{
                "callback": {
                    "url": f"http://127.0.0.1:{port}/cb",
                    "auth_type": "none",
                    "secret_env": "",
                }
            },
        )
        app = _make_app(
            tmp_path, consumers=[profile], vlm_provider="mock", vlm_mock_behavior="live"
        )
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            # Server-authoritative liveness (LIVE) -> canonical PASS -> portrait.
            bh = _live_portrait(client, cookies)
            # submit
            res = client.post("/api/v1/browser/submit", headers=bh)
            assert res.status_code == 200, res.text
            assert res.json()["redirect_url"] == "http://localhost:3001/complete"
            # double submit dedup -> same redirect, no second callback
            sent_bytes = received["body"]
            client.post("/api/v1/browser/submit", headers=bh)
            assert received["body"] == sent_bytes
            # status completed
            status = client.get(
                "/api/v1/integration/transactions/ext-123/status?source=D365",
                headers=_dev_headers(),
            )
            assert status.json()["status"] == "COMPLETED"
    finally:
        server.shutdown()


def _internal_tx_id(client: TestClient, status_response) -> str:
    # resolve via external index
    index = client.app.state.integration_index_store
    mapping = index.get_external(external_key_hash("D365", "ext-123"))
    return mapping["internal_transaction_id"]


def test_completed_reopen_terminal(tmp_path) -> None:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = dict(
            D365,
            **{
                "callback": {
                    "url": f"http://127.0.0.1:{port}/cb",
                    "auth_type": "none",
                    "secret_env": "",
                }
            },
        )
        app = _make_app(
            tmp_path, consumers=[profile], vlm_provider="mock", vlm_mock_behavior="live"
        )
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            bh = _live_portrait(client, cookies)
            assert client.post("/api/v1/browser/submit", headers=bh).status_code == 200
            # reopen via reissue -> TERMINAL completed session, cannot mutate
            reissue = client.post(
                "/api/v1/integration/transactions/ext-123/launch-sessions?source=D365",
                headers=_dev_headers(),
            )
            assert reissue.status_code == 200, reissue.text
            reopen = _redeem(client, _launch_url_token(reissue.json()["launch_url"]))
            cookies2 = _cookies_from_response(reopen)
            state = client.get(
                "/api/v1/browser/session",
                headers={"Cookie": f"lp_session={cookies2['lp_session']}"},
            )
            assert state.json()["state"] == "completed"
            res = client.post(
                "/api/v1/browser/attempts",
                data={"attempt_id": "x1", "result": "QUALITY_RETRY", "reason_code": "BLURRED"},
                headers=_browser_headers(cookies2["lp_session"], cookies2["lp_csrf"]),
            )
            assert res.status_code == 409
    finally:
        server.shutdown()


# ------------------------------------------------- callback/redaction unit
def test_callback_event_id_stable() -> None:
    assert build_callback_event_id("D365", "ext-1") == build_callback_event_id("D365", "ext-1")
    assert build_callback_event_id("D365", "ext-1") != build_callback_event_id("D365", "ext-2")


def test_redaction_base64() -> None:
    from app.core.logging import redact_value

    assert redact_value("processed_jpeg_base64", "SENTINEL") == "[REDACTED]"
    assert redact_value("csrf_token", "SENTINEL") == "[REDACTED]"
    assert redact_value("callback_secret", "SENTINEL") == "[REDACTED]"


def test_safe_request_path_redacts_token() -> None:
    from app.core.middleware import _safe_request_path

    scope: dict[str, Any] = {"path": "/xbiz/live_photo/l/TOKENSENTINEL"}
    assert "TOKENSENTINEL" not in _safe_request_path(scope)
    assert _safe_request_path(scope) == "/xbiz/live_photo/l/{token}"


def test_portrait_integrity_and_base64_not_persisted(tmp_path) -> None:
    # Base64 is never persisted to the transaction folder after submit.
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            received["body"] = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

        def log_message(self, *args: Any) -> None:
            pass

    received: dict[str, Any] = {}
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = dict(
            D365,
            **{
                "callback": {
                    "url": f"http://127.0.0.1:{port}/cb",
                    "auth_type": "none",
                    "secret_env": "",
                }
            },
        )
        app = _make_app(
            tmp_path, consumers=[profile], vlm_provider="mock", vlm_mock_behavior="live"
        )
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            bh = _live_portrait(client, cookies)
            assert client.post("/api/v1/browser/submit", headers=bh).status_code == 200
            payload = json.loads(received["body"])
            decoded = base64.b64decode(payload["processed_jpeg_base64"])
            assert decoded == _jpeg_bytes() or decoded.startswith(b"\xff\xd8\xff")
            import hashlib

            assert payload["processed_jpeg_sha256"] == hashlib.sha256(decoded).hexdigest()
            # base64 sentinel not persisted in any transaction file
            store: TransactionFileStore = app.state.transaction_store
            tx_id = _internal_tx_id(client, None)
            base64_str = payload["processed_jpeg_base64"]
            for root, _dirs, files in os.walk(store.transaction_dir(tx_id)):
                for name in files:
                    if name == "processed.jpg":
                        continue
                    content = (Path(root) / name).read_bytes()
                    assert base64_str.encode() not in content
    finally:
        server.shutdown()


def test_profile_max_attempts_enforced(tmp_path) -> None:
    profile = dict(D365, max_attempts=2)
    app = _make_app(tmp_path, consumers=[profile])
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _attempts(client, cookies, "a1", "BLURRED")
        res = _attempts(client, cookies, "a2", "BLURRED")
        assert res.json()["terminal"] is True
        res = client.get(
            "/api/v1/integration/transactions/ext-123/status?source=D365", headers=_dev_headers()
        )
        assert res.json()["max_attempts"] == 2


def test_launch_concurrent_duplicate_only_one_created(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    app = _make_app(tmp_path)
    statuses: list[int] = []

    def do_launch() -> int:
        with TestClient(app) as client:
            return client.post(
                "/api/v1/integration/launch-sessions",
                json={"transaction_id": "concurrent-1", "source": "D365"},
                headers=_dev_headers(),
            ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: do_launch(), range(4)))

    assert sorted(statuses).count(200) == 1
    assert statuses.count(409) == 3
    store: TransactionFileStore = app.state.transaction_store
    tx_dir = store.root / "transactions"
    assert sum(1 for _ in tx_dir.iterdir()) == 1


def test_redaction_m58_keys() -> None:
    from app.core.logging import redact_value, safe_headers

    assert redact_value("lp_session", "SENTINEL") == "[REDACTED]"
    assert redact_value("lp_csrf", "SENTINEL") == "[REDACTED]"
    assert redact_value("x-livephoto-dev-auth", "SENTINEL") == "[REDACTED]"
    assert "x-livephoto-dev-auth" not in safe_headers({"x-livephoto-dev-auth": "SENTINEL"})


# ---------------------------------------------------- callback / redirect unit
def test_validate_redirect_url_exact_origin() -> None:
    from app.integrations.callback import validate_redirect_url
    from app.integrations.consumers import ConsumerProfile

    profile = ConsumerProfile(
        consumer_id="D365",
        allowed_redirect_origins=["https://consumer.example.test", "http://localhost:3001"],
    )
    assert validate_redirect_url(profile, "https://consumer.example.test/complete", local=False)
    assert validate_redirect_url(profile, "http://localhost:3001/complete", local=True)
    # approved origin + query is allowed (a query string is not an open-redirect vector)
    assert validate_redirect_url(
        profile, "https://consumer.example.test/path?code=abc123", local=False
    )
    # subdomain / substring / endsWith must NOT match
    assert not validate_redirect_url(
        profile, "https://consumer.example.test.evil.com/", local=False
    )
    assert not validate_redirect_url(profile, "https://evil-consumer.example.test/", local=False)
    assert not validate_redirect_url(profile, "https://consumer.example.test:8443/", local=False)
    # http disallowed outside local; userinfo/fragment/schemes rejected
    assert not validate_redirect_url(profile, "http://consumer.example.test/", local=False)
    assert not validate_redirect_url(profile, "https://user@consumer.example.test/", local=False)
    assert not validate_redirect_url(profile, "https://consumer.example.test/#f", local=False)
    assert not validate_redirect_url(profile, "javascript:alert(1)", local=False)
    assert not validate_redirect_url(profile, "data:text/html,hi", local=False)
    assert not validate_redirect_url(profile, "", local=False)


def _serving_server(handler):
    import http.server

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            handler(self)

        def log_message(self, *args: Any) -> None:
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, srv.server_address[1]


def _run_callback_server(status: int, body: bytes, counter: list[int]):
    def h(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        counter[0] += 1
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    return h


def test_send_callback_transient_retry_then_success() -> None:
    import asyncio

    from app.core.config import Settings
    from app.integrations.callback import build_callback_payload, send_callback
    from app.integrations.consumers import ConsumerProfile

    calls: list[int] = [0]
    statuses = iter([500, 500, 200])

    def h(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        calls[0] += 1
        code = next(statuses)
        if code == 200:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')
        else:
            self.send_response(500)
            self.end_headers()

    srv, port = _serving_server(h)
    try:
        profile = ConsumerProfile(
            consumer_id="D365",
            callback={"url": f"http://127.0.0.1:{port}/cb", "auth_type": "none", "secret_env": ""},
        )
        settings = Settings(
            _env_file=None, app_env="test", callback_max_retries=2, callback_timeout_seconds=2
        )
        payload = build_callback_payload(
            event_id="e",
            external_transaction_id="x",
            decision_id="d",
            processed_jpeg=b"\xff\xd8\xff",
            occurred_at="now",
        )
        result = asyncio.run(send_callback(settings, profile, payload))
        assert result.acknowledged is True
        assert calls[0] == 3  # 500,500,200 -> retried twice then success
    finally:
        srv.shutdown()


def test_send_callback_400_no_retry() -> None:
    import asyncio

    from app.core.config import Settings
    from app.integrations.callback import (
        CallbackTerminalError,
        build_callback_payload,
        send_callback,
    )
    from app.integrations.consumers import ConsumerProfile

    calls: list[int] = [0]

    def h(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        calls[0] += 1
        self.send_response(400)
        self.end_headers()

    srv, port = _serving_server(h)
    try:
        profile = ConsumerProfile(
            consumer_id="D365",
            callback={"url": f"http://127.0.0.1:{port}/cb", "auth_type": "none", "secret_env": ""},
        )
        settings = Settings(
            _env_file=None, app_env="test", callback_max_retries=2, callback_timeout_seconds=2
        )
        payload = build_callback_payload(
            event_id="e",
            external_transaction_id="x",
            decision_id="d",
            processed_jpeg=b"\xff\xd8\xff",
            occurred_at="now",
        )
        try:
            asyncio.run(send_callback(settings, profile, payload))
            raise AssertionError("expected terminal error")
        except CallbackTerminalError:
            pass
        assert calls[0] == 1  # no retry on deterministic 4xx
    finally:
        srv.shutdown()


def test_send_callback_bearer_env_auth() -> None:
    import asyncio

    from app.core.config import Settings
    from app.integrations.callback import build_callback_payload, send_callback
    from app.integrations.consumers import ConsumerProfile

    captured: dict[str, Any] = {}

    def h(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        captured["auth"] = self.headers.get("Authorization")
        captured["idem"] = self.headers.get("Idempotency-Key")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

    srv, port = _serving_server(h)
    os.environ["TEST_CB_TOKEN"] = "super-secret"
    try:
        profile = ConsumerProfile(
            consumer_id="D365",
            callback={
                "url": f"http://127.0.0.1:{port}/cb",
                "auth_type": "bearer_env",
                "secret_env": "TEST_CB_TOKEN",
            },
        )
        settings = Settings(
            _env_file=None, app_env="test", callback_max_retries=1, callback_timeout_seconds=2
        )
        payload = build_callback_payload(
            event_id="eid-1",
            external_transaction_id="x",
            decision_id="d",
            processed_jpeg=b"\xff\xd8\xff",
            occurred_at="now",
        )
        asyncio.run(send_callback(settings, profile, payload))
        assert captured["auth"] == "Bearer super-secret"
        assert captured["idem"] == "eid-1"
    finally:
        os.environ.pop("TEST_CB_TOKEN", None)
        srv.shutdown()


def test_send_callback_302_not_followed() -> None:
    import asyncio

    from app.core.config import Settings
    from app.integrations.callback import (
        CallbackTerminalError,
        build_callback_payload,
        send_callback,
    )
    from app.integrations.consumers import ConsumerProfile

    def h(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(302)
        self.send_header("Location", "http://evil.example/")
        self.end_headers()

    srv, port = _serving_server(h)
    try:
        profile = ConsumerProfile(
            consumer_id="D365",
            callback={"url": f"http://127.0.0.1:{port}/cb", "auth_type": "none", "secret_env": ""},
        )
        settings = Settings(
            _env_file=None, app_env="test", callback_max_retries=1, callback_timeout_seconds=2
        )
        payload = build_callback_payload(
            event_id="e",
            external_transaction_id="x",
            decision_id="d",
            processed_jpeg=b"\xff\xd8\xff",
            occurred_at="now",
        )
        try:
            asyncio.run(send_callback(settings, profile, payload))
            raise AssertionError("expected terminal error for 3xx")
        except CallbackTerminalError:
            pass
    finally:
        srv.shutdown()


# ---------------------------------------------- VLM LIVE must not authorize submit
def test_vlm_live_alone_does_not_authorize_submit(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _redeem_and_capture(client)
        # write a LIVE experimental VLM result (no canonical decision)
        store = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        import json as _json

        from app.transactions import ArtifactType

        store.write_artifact(
            internal,
            ArtifactType.VLM_RESULT,
            _json.dumps({"classification": "LIVE", "provider": "mock"}).encode(),
            content_type="application/json",
        )
        res = client.post(
            "/api/v1/browser/submit",
            headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
        )
        assert res.status_code == 412
        assert res.json()["error"]["code"] == "NOT_READY"


# ----------------------------------------------------------- cookie attributes
def test_cookie_attributes(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
        resp = _redeem(client, _launch_url_token(body["launch_url"]))
        set_cookie = resp.headers.get_list("set-cookie")
        raw = "\n".join(set_cookie)
        assert "lp_session" in raw and "HttpOnly" in raw
        assert "SameSite=strict" in raw
        assert "lp_csrf" in raw and "HttpOnly" not in raw.split("lp_csrf")[1].split(";")[0]


# ---------------------------------------------------------- EXPIRED redemption
def test_expired_redemption_outcome(tmp_path) -> None:
    app = _make_app(tmp_path, launch_token_ttl_seconds=1)
    with TestClient(app) as client:
        body = _launch(client)
        import time

        time.sleep(1.1)
        resp = _redeem(client, _launch_url_token(body["launch_url"]))
        cookies = _cookies_from_response(resp)
        assert cookies.get("lp_launch_outcome") == "EXPIRED"


# ----------------------------------------------- integration index confinement
def test_index_confinement_symlink(tmp_path) -> None:
    from app.integrations.store import IntegrationIndexError, IntegrationIndexStore

    store = IntegrationIndexStore(str(tmp_path / "storage"))
    store.initialize()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "leak.json"
    target.write_text("{}")
    import os

    link = store.root / "index" / "launch-tokens" / "symlink.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(target), link)
    try:
        store.get_launch_token("symlink")
        raise AssertionError("expected confinement failure")
    except IntegrationIndexError:
        pass


def test_concurrent_submit_single_callback(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    delivered: list[int] = [0]

    def h(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        delivered[0] += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

    srv, port = _serving_server(h)
    try:
        profile = dict(
            D365,
            **{
                "callback": {
                    "url": f"http://127.0.0.1:{port}/cb",
                    "auth_type": "none",
                    "secret_env": "",
                }
            },
        )
        app = _make_app(
            tmp_path, consumers=[profile], vlm_provider="mock", vlm_mock_behavior="live"
        )
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            _live_portrait(client, cookies)

            def submit() -> int:
                with TestClient(app) as c:
                    return c.post(
                        "/api/v1/browser/submit",
                        headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
                    ).status_code

            with ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(lambda _: submit(), range(4)))
            assert statuses.count(200) >= 1
            assert delivered[0] == 1  # exactly one callback delivered
            status = client.get(
                "/api/v1/integration/transactions/ext-123/status?source=D365",
                headers=_dev_headers(),
            )
            assert status.json()["status"] == "COMPLETED"
    finally:
        srv.shutdown()


def test_consumer_profiles_path_default_resolves_from_backend_cwd(tmp_path) -> None:
    """The committed example path resolves and loads when running from the backend/ cwd.

    Settings default is ``config/consumers.example.json`` (relative to the backend process cwd),
    matching the documented local startup directory (``backend/``).
    """
    from pathlib import Path

    from app.core.config import Settings
    from app.integrations.consumers import load_consumer_profiles

    settings = Settings(_env_file=None, app_env="test", file_storage_root=str(tmp_path / "s"))
    path = Path(settings.consumer_profiles_path)
    assert path.is_absolute() is False
    assert path.exists(), f"default consumer path does not resolve from cwd: {path}"
    profiles = load_consumer_profiles(str(path), settings.app_env)
    assert len(profiles) >= 1
    assert profiles[0].consumer_id == "D365"


def test_validate_redirect_url_malformed_port_rejected() -> None:
    from app.integrations.callback import validate_redirect_url
    from app.integrations.consumers import ConsumerProfile

    profile = ConsumerProfile(
        consumer_id="D365", allowed_redirect_origins=["https://consumer.example.test"]
    )
    # Out-of-range / non-numeric ports must be validation failures, not exceptions.
    assert (
        validate_redirect_url(profile, "https://consumer.example.test:99999/", local=False) is False
    )
    assert (
        validate_redirect_url(profile, "https://consumer.example.test:abc/", local=False) is False
    )


def test_quality_eligible_accepted_and_counts(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = client.post(
            "/api/v1/browser/attempts",
            data={"attempt_id": "qe-1", "result": "QUALITY_ELIGIBLE"},
            headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
        )
        assert res.status_code == 200, res.text
        assert res.json()["attempt_count"] == 1
        # No selected-original is persisted from a quality-eligible registration alone.
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert store.artifact_exists(internal, "capture/selected-original.jpg") is False
        assert store.read_transaction_json(internal)["status"] != "CAPTURE_READY"


def test_quality_eligible_then_capture_dedups(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        r = client.post(
            "/api/v1/browser/attempts",
            data={"attempt_id": "qe-2", "result": "QUALITY_ELIGIBLE"},
            headers=bh,
        )
        assert r.json()["attempt_count"] == 1
        # Same attempt_id on /browser/capture must not increment again.
        res = client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "qe-2", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        assert res.status_code == 200
        assert res.json()["attempt_count"] == 1
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert store.artifact_exists(internal, "capture/selected-original.jpg") is True


def test_quality_eligible_with_security_reason_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = client.post(
            "/api/v1/browser/attempts",
            data={"attempt_id": "qe-3", "result": "QUALITY_ELIGIBLE", "reason_code": "LIVE"},
            headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
        )
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "DISALLOWED_REASON"


def test_quality_eligible_no_authority(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/attempts",
            data={"attempt_id": "qe-4", "result": "QUALITY_ELIGIBLE"},
            headers=bh,
        )
        # QUALITY_ELIGIBLE never authorizes Submit (no canonical PASS exists).
        res = client.post("/api/v1/browser/submit", headers=bh)
        assert res.status_code == 412
        assert res.json()["error"]["code"] == "NOT_READY"


def test_capture_same_attempt_id_second_upload_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        first = client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "up-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        assert first.status_code == 200
        # A second upload with the SAME attempt_id must be rejected (one upload per attempt) so a
        # client cannot overwrite selected-original repeatedly without consuming attempts.
        second = client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "up-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(64, 64), "image/jpeg")},
            headers=bh,
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "UPLOAD_ALREADY_RECORDED"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert store.read_transaction_json(internal)["status"] == "CAPTURE_READY"


def test_concurrent_capture_same_attempt_id_single_upload(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    app = _make_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        session_cookie = cookies["lp_session"]
        csrf = cookies["lp_csrf"]

        def do_upload() -> int:
            with TestClient(app) as c:
                return c.post(
                    "/api/v1/browser/capture",
                    data={"attempt_id": "conc-up", "face_box": _FACE_BOX},
                    files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
                    headers=_browser_headers(session_cookie, csrf),
                ).status_code

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(lambda _: do_upload(), range(4)))

    assert statuses.count(200) == 1  # exactly one accepted upload
    assert statuses.count(409) == 3  # the rest rejected (one upload per attempt)
    store: TransactionFileStore = app.state.transaction_store
    internal = _internal_tx_id(client, None)
    attempts = store.read_json(internal, "attempts.json")
    assert attempts["attempt_count"] == 1
    assert len(attempts["uploaded_attempt_ids"]) == 1


# ------------------------------------------------------- browser liveness (pre-M6 Groq gate)
def _liveness_app(tmp_path, **overrides: object):
    kwargs = {
        "vlm_provider": "mock",
        "vlm_mock_behavior": "live",
        "vlm_timeout_seconds": 1.0,
    }
    kwargs.update(overrides)
    return _make_app(tmp_path, **kwargs)


def _capture_and_liveness(
    client: TestClient,
    cookies: dict[str, str],
    attempt_id: str,
    jpeg: bytes | None = None,
    face_box: str = _FACE_BOX,
):
    bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
    cap = client.post(
        "/api/v1/browser/capture",
        data={"attempt_id": attempt_id, "face_box": face_box},
        files={"selected_image": ("sel.jpg", jpeg or _jpeg_bytes(), "image/jpeg")},
        headers=bh,
    )
    assert cap.status_code == 200, cap.text
    return client.post("/api/v1/browser/liveness", data={"attempt_id": attempt_id}, headers=bh)


def test_browser_liveness_requires_session(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        res = client.post("/api/v1/browser/liveness", data={"attempt_id": "a1"})
        assert res.status_code == 401


def test_browser_liveness_requires_csrf(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = client.post(
            "/api/v1/browser/liveness",
            data={"attempt_id": "a1"},
            headers={"Cookie": f"lp_session={cookies['lp_session']}"},
        )
        assert res.status_code == 403


def test_browser_liveness_uses_configured_provider_not_browser(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "a1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        # The browser-supplied provider/behavior fields are ignored by the endpoint; the configured
        # settings provider (mock) produced the result (LIVE via settings.vlm_mock_behavior).
        res = client.post(
            "/api/v1/browser/liveness",
            data={"attempt_id": "a1", "provider": "gemini", "mock_behavior": "screen_replay"},
            headers=bh,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "PASS"
        assert body["portrait_allowed"] is True


def test_browser_liveness_live_writes_canonical_pass_and_portrait(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200, res.text
        assert res.json()["outcome"] == "PASS"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        decision = read_decision(store, internal)
        assert decision is not None and decision.outcome.value == "PASS"
        assert decision.decision_source == "vlm"
        assert decision.metadata.get("provider") == "mock"
        # LIVE -> portrait endpoint succeeds.
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        portrait = client.post("/api/v1/browser/portrait", headers=bh)
        assert portrait.status_code == 200, portrait.text


def test_browser_liveness_non_live_no_pass_portrait_blocked(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="screen_replay")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200
        body = res.json()
        assert body["classification"] == "SCREEN_REPLAY"
        assert body["outcome"] == "FAIL"
        assert body["portrait_allowed"] is False
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        assert read_decision(store, internal).outcome.value == "FAIL"
        # Portrait must still be blocked server-side (no canonical PASS).
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        portrait = client.post("/api/v1/browser/portrait", headers=bh)
        assert portrait.status_code == 412


@pytest.mark.parametrize(
    ("behavior", "expected_outcome"),
    [
        ("print", "FAIL"),
        ("quality_failure", "RETRY"),
        ("uncertain", "RETRY"),
    ],
)
def test_browser_liveness_mapping(tmp_path, behavior: str, expected_outcome: str) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior=behavior)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200
        body = res.json()
        assert body["portrait_allowed"] is False
        assert body["outcome"] == expected_outcome
        # No portrait for non-LIVE.
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412


def test_browser_liveness_provider_failure_no_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="auth")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 502
        assert res.json()["error"]["code"] == "LIVENESS_UNAVAILABLE"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        decision = read_decision(store, internal)
        # Fail closed: no PASS, no decision.
        assert decision is None or decision.outcome.value != "PASS"
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412


def test_browser_liveness_idempotent_single_provider_call(tmp_path, monkeypatch) -> None:
    from app.experiments.vlm import VlmEvaluationService

    calls: list[int] = [0]
    original = VlmEvaluationService.evaluate

    async def counting_evaluate(self, request):
        calls[0] += 1
        return await original(self, request)

    monkeypatch.setattr(VlmEvaluationService, "evaluate", counting_evaluate)
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "idem-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        first = client.post("/api/v1/browser/liveness", data={"attempt_id": "idem-1"}, headers=bh)
        second = client.post("/api/v1/browser/liveness", data={"attempt_id": "idem-1"}, headers=bh)
        assert first.status_code == 200 and second.status_code == 200
        assert first.json() == second.json()
    assert calls[0] == 1  # second evaluation served from persisted record


def test_browser_liveness_new_capture_fresh_evaluation(tmp_path, monkeypatch) -> None:
    from app.experiments.vlm import VlmEvaluationService

    calls: list[int] = [0]
    original = VlmEvaluationService.evaluate

    async def counting_evaluate(self, request):
        calls[0] += 1
        return await original(self, request)

    monkeypatch.setattr(VlmEvaluationService, "evaluate", counting_evaluate)
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "cap-1")
        # A NEW capture (new attempt id + new image) must trigger a fresh evaluation.
        _capture_and_liveness(client, cookies, "cap-2", _jpeg_bytes(64, 64))
    assert calls[0] == 2


def test_liveness_service_blocked_in_production(tmp_path) -> None:
    """The authoritative liveness service refuses to operate in production (providers blocked)."""
    import pytest as _pytest_module

    settings = Settings(
        _env_file=None,
        app_env="production",
        vlm_provider="mock",
        file_storage_root=str(tmp_path / "s"),
        vlm_experiment_enabled=True,
    )
    store = TransactionFileStore(str(tmp_path / "s"))
    store.initialize()
    from app.transactions import ArtifactType

    tx_id = "0" * 32
    store.create_transaction(tx_id, {"transaction_id": tx_id, "status": "CAPTURE_READY"})
    store.write_artifact(
        tx_id,
        ArtifactType.SELECTED_ORIGINAL_CAPTURE,
        _jpeg_bytes(),
        content_type="image/jpeg",
    )
    from app.experiments.vlm import liveness
    from app.providers.vision import VlmError, VlmErrorCode

    with _pytest_module.raises(VlmError) as exc_info:
        import asyncio

        asyncio.run(
            liveness.evaluate_capture(settings, store, tx_id, attempt_id="a1", selected_sha256="s")
        )
    assert exc_info.value.code == VlmErrorCode.VLM_DISABLED


def test_customer_xbiz_path_works_without_test_writer(tmp_path) -> None:
    """Acceptance: DECISION_TEST_WRITER_ENABLED=false still completes the xbiz happy path when the
    authoritative provider (mock, LIVE) confirms liveness — Groq, not the test PASS writer, gates
    portrait eligibility."""
    delivered: list[int] = [0]

    def h(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        delivered[0] += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

    srv, port = _serving_server(h)
    try:
        profile = dict(
            D365,
            **{
                "callback": {
                    "url": f"http://127.0.0.1:{port}/cb",
                    "auth_type": "none",
                    "secret_env": "",
                }
            },
        )
        app = _make_app(
            tmp_path,
            consumers=[profile],
            decision_test_writer_enabled=False,
            vlm_provider="mock",
            vlm_mock_behavior="live",
        )
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            client.post(
                "/api/v1/browser/capture",
                data={"attempt_id": "ok-1", "face_box": _FACE_BOX},
                files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
                headers=bh,
            )
            liv = client.post("/api/v1/browser/liveness", data={"attempt_id": "ok-1"}, headers=bh)
            assert liv.status_code == 200, liv.text
            assert liv.json()["portrait_allowed"] is True
            portrait = client.post("/api/v1/browser/portrait", headers=bh)
            assert portrait.status_code == 200, portrait.text
            submit = client.post("/api/v1/browser/submit", headers=bh)
            assert submit.status_code == 200, submit.text
            assert submit.json()["redirect_url"] == "http://localhost:3001/complete"
            assert delivered[0] == 1
            # The dev test-writer route is NOT registered (flag false).
            assert client.post("/api/v1/dev/test-decision").status_code == 404
    finally:
        srv.shutdown()


# ------------------------------------------------------- pre-M6 hardening tests (A-G)


def _bound_pass_decision(app, internal_tx_id: str, attempt_id: str, image_sha: str) -> None:
    """Write a canonical PASS bound to an arbitrary (attempt, sha) to simulate a stale promotion."""
    from app.transactions.decisions import build_decision, write_decision

    store = app.state.transaction_store
    identity = hashlib.sha256(f"{attempt_id}:{image_sha}".encode()).hexdigest()
    decision = build_decision(
        internal_tx_id,
        outcome="PASS",
        source="vlm",
        version="liveness-v1",
        metadata={
            "attempt_id": attempt_id,
            "selected_sha256": image_sha,
            "liveness_identity": identity,
        },
    )
    write_decision(store, internal_tx_id, decision)


def _capture(client: TestClient, cookies: dict[str, str], attempt_id: str, jpeg: bytes) -> None:
    res = client.post(
        "/api/v1/browser/capture",
        data={"attempt_id": attempt_id, "face_box": _FACE_BOX},
        files={"selected_image": ("sel.jpg", jpeg, "image/jpeg")},
        headers=_browser_headers(cookies["lp_session"], cookies["lp_csrf"]),
    )
    assert res.status_code == 200, res.text


def _session_ready(client: TestClient, cookies: dict[str, str]) -> bool:
    state = client.get(
        "/api/v1/browser/session", headers={"Cookie": f"lp_session={cookies['lp_session']}"}
    ).json()
    return bool(state.get("submission_ready"))


def test_hardening_stale_authorization_invalidated_on_new_capture(tmp_path) -> None:
    app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        # Attempt 1 -> LIVE -> PASS -> portrait A.
        _capture(client, cookies, "a1", _jpeg_bytes())
        assert (
            client.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"] is True
        )
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 200
        assert _session_ready(client, cookies) is True

        # Attempt 2 / new capture -> previous PASS + portrait must be invalidated immediately.
        _capture(client, cookies, "a2", _jpeg_bytes(64, 64))
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        assert read_decision(store, internal) is None  # PASS removed
        assert (
            store.artifact_exists(internal, "portrait/processed.jpg") is False
        )  # portrait removed
        assert _session_ready(client, cookies) is False
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412
        assert client.post("/api/v1/browser/submit", headers=bh).status_code == 412
        # GET /browser/portrait must not return the old portrait A.
        assert client.get("/api/v1/browser/portrait", headers=bh).status_code == 404


def test_hardening_new_pass_cannot_reuse_old_portrait(tmp_path) -> None:
    app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        # attempt 1 LIVE -> portrait A.
        _capture(client, cookies, "a1", _jpeg_bytes())
        assert (
            client.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"] is True
        )
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 200

        # attempt 2 -> new capture + LIVE -> new PASS (bound to B), but portrait B not yet made.
        _capture(client, cookies, "a2", _jpeg_bytes(64, 64))
        assert (
            client.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"] is True
        )
        # Before portrait B: submit NOT_READY; old portrait A not exposed.
        assert client.post("/api/v1/browser/submit", headers=bh).status_code == 412
        assert client.get("/api/v1/browser/portrait", headers=bh).status_code == 404
        # Generate portrait B -> submit succeeds.
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 200
        assert _session_ready(client, cookies) is True


def test_hardening_stale_in_flight_result_not_promoted(tmp_path) -> None:
    import threading as _th

    from app.experiments.vlm import VlmEvaluationService

    original = VlmEvaluationService.evaluate
    provider_started = _th.Event()
    release_provider = _th.Event()
    calls: list[int] = []

    async def delayed_evaluate(self, request):
        calls.append(1)
        provider_started.set()
        release_provider.wait(timeout=15)
        return await original(self, request)

    app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
    VlmEvaluationService.evaluate = delayed_evaluate  # type: ignore[method-assign]
    try:
        cookies_holder: dict[str, str] = {}
        result_holder: dict[str, int] = {}

        def attempt1_liveness() -> None:
            with TestClient(app) as c:
                cookies = _active_cookies(c)
                cookies_holder.update(cookies)
                bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
                _capture(c, cookies, "a1", _jpeg_bytes())
                result_holder["status"] = c.post("/api/v1/browser/liveness", headers=bh).status_code

        t1 = _th.Thread(target=attempt1_liveness)
        t1.start()
        assert provider_started.wait(timeout=10)

        # While attempt-1's provider call is in flight, upload attempt 2 in the SAME transaction.
        internal: str
        with TestClient(app) as c2:
            cookies2 = dict(cookies_holder)  # reuse the same session/transaction
            assert cookies2
            _capture(c2, cookies2, "a2", _jpeg_bytes(64, 64))
            internal = _internal_tx_id(c2, None)
            from app.transactions.decisions import read_decision

            assert read_decision(c2.app.state.transaction_store, internal) is None

        # Let the attempt-1 provider return LIVE.
        release_provider.set()
        t1.join(timeout=15)
        assert result_holder.get("status") in (409, 502)  # stale/conflict, never promoted

        with TestClient(app) as c3:
            store: TransactionFileStore = app.state.transaction_store
            from app.transactions.decisions import read_decision

            assert read_decision(store, internal) is None  # attempt-1 result was NOT promoted
            # Attempt-2 portrait remains blocked (no current PASS).
            bh2 = _browser_headers(cookies2["lp_session"], cookies2["lp_csrf"])
            assert c3.post("/api/v1/browser/portrait", headers=bh2).status_code == 412
        assert len(calls) == 1
    finally:
        VlmEvaluationService.evaluate = original  # type: ignore[method-assign]


def test_hardening_concurrent_liveness_single_provider_call(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from app.experiments.vlm import VlmEvaluationService

    original = VlmEvaluationService.evaluate
    calls: list[int] = []

    async def slow_evaluate(self, request):
        calls.append(1)
        await asyncio.sleep(0.3)
        return await original(self, request)

    VlmEvaluationService.evaluate = slow_evaluate  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            _capture(client, cookies, "c1", _jpeg_bytes())
            session_cookie = cookies["lp_session"]
            csrf = cookies["lp_csrf"]

            def call() -> int:
                with TestClient(app) as c:
                    return c.post(
                        "/api/v1/browser/liveness",
                        headers=_browser_headers(session_cookie, csrf),
                    ).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(lambda _: call(), range(2)))
            assert sorted(statuses) == [200, 202]  # one completed, one observed in-progress
        assert len(calls) == 1  # exactly one provider call
    finally:
        VlmEvaluationService.evaluate = original  # type: ignore[method-assign]


def test_hardening_client_cannot_manipulate_identity(tmp_path) -> None:
    from app.experiments.vlm import VlmEvaluationService

    original = VlmEvaluationService.evaluate
    calls: list[int] = []

    async def counting(self, request):
        calls.append(1)
        return await original(self, request)

    VlmEvaluationService.evaluate = counting  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            _capture(client, cookies, "real-1", _jpeg_bytes())
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            # The endpoint ignores any client-supplied attempt_id; identity is server-derived.
            r1 = client.post("/api/v1/browser/liveness", data={"attempt_id": "fake-x"}, headers=bh)
            assert r1.status_code == 200
            r2 = client.post("/api/v1/browser/liveness", data={"attempt_id": "fake-y"}, headers=bh)
            assert r2.status_code == 200
            assert r1.json() == r2.json()
        assert len(calls) == 1  # fake attempt ids cannot trigger extra evaluations
    finally:
        VlmEvaluationService.evaluate = original  # type: ignore[method-assign]


def test_hardening_provider_error_cached_single_call(tmp_path) -> None:
    from app.experiments.vlm import VlmEvaluationService

    original = VlmEvaluationService.evaluate
    calls: list[int] = []

    async def failing_once(self, request):
        calls.append(1)
        from app.providers.vision import VlmError, VlmErrorCode

        raise VlmError(VlmErrorCode.PROVIDER_TIMEOUT, "boom")

    VlmEvaluationService.evaluate = failing_once  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            _capture(client, cookies, "e1", _jpeg_bytes())
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            first = client.post("/api/v1/browser/liveness", headers=bh)
            assert first.status_code in (502, 503)
            second = client.post("/api/v1/browser/liveness", headers=bh)
            assert second.status_code in (502, 503)  # cached fail-closed; provider NOT called again
            assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412
        assert len(calls) == 1  # the repeat did not consume another provider request
    finally:
        VlmEvaluationService.evaluate = original  # type: ignore[method-assign]


def test_hardening_old_image_decision_not_current_after_new_capture(tmp_path) -> None:
    app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        _capture(client, cookies, "a1", _jpeg_bytes())
        assert (
            client.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"] is True
        )
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        old_decision = read_decision(store, internal)
        assert old_decision is not None and old_decision.outcome.value == "PASS"

        # New capture invalidates the old decision.
        _capture(client, cookies, "a2", _jpeg_bytes(64, 64))
        assert liveness.has_current_canonical_pass(store, internal) is False
        # A stale decision bound to the OLD image SHA must NOT satisfy the current check.
        _bound_pass_decision(app, internal, "a1", old_decision.metadata["selected_sha256"])
        assert liveness.has_current_canonical_pass(store, internal) is False


# ------------------------------------------------------- stale-portrait race tests


def test_portrait_race_new_capture_supersedes_inflight(tmp_path) -> None:
    """A stale in-flight portrait must never be authorized for a newer capture or overwrite it."""
    import threading as _th

    from app.portrait import PortraitProcessor

    received: dict[str, Any] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            received["body"] = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    original = PortraitProcessor.process
    portrait_started = _th.Event()
    release_portrait = _th.Event()
    portrait_calls: list[int] = []

    async def delayed_process(
        self, source, transaction_id, *, face_box_normalized=None, output_relative_path=None
    ):
        portrait_calls.append(1)
        if len(portrait_calls) == 1:  # only A's portrait is delayed
            portrait_started.set()
            release_portrait.wait(timeout=15)
        return await original(
            self,
            source,
            transaction_id,
            face_box_normalized=face_box_normalized,
            output_relative_path=output_relative_path,
        )

    PortraitProcessor.process = delayed_process  # type: ignore[method-assign]
    try:
        profile = dict(
            D365,
            **{
                "callback": {
                    "url": f"http://127.0.0.1:{port}/cb",
                    "auth_type": "none",
                    "secret_env": "",
                }
            },
        )
        app = _make_app(
            tmp_path, consumers=[profile], vlm_provider="mock", vlm_mock_behavior="live"
        )
        cookies_holder: dict[str, str] = {}
        portrait_a_status: dict[str, int] = {}

        def attempt_a_portrait() -> None:
            with TestClient(app) as c:
                cookies = _active_cookies(c)
                cookies_holder.update(cookies)
                bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
                _capture(c, cookies, "a1", _jpeg_bytes())
                assert c.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"]
                portrait_a_status["status"] = c.post(
                    "/api/v1/browser/portrait", headers=bh
                ).status_code

        t1 = _th.Thread(target=attempt_a_portrait)
        t1.start()
        assert portrait_started.wait(timeout=10)

        # While A's portrait is processing, upload B and fully promote B's portrait.
        with TestClient(app) as c2:
            cookies2 = dict(cookies_holder)
            _capture(c2, cookies2, "a2", _jpeg_bytes(64, 64))
            bh2 = _browser_headers(cookies2["lp_session"], cookies2["lp_csrf"])
            assert c2.post("/api/v1/browser/liveness", headers=bh2).json()["portrait_allowed"]
            assert c2.post("/api/v1/browser/portrait", headers=bh2).status_code == 200
            internal = _internal_tx_id(c2, None)
            store = c2.app.state.transaction_store
            from app.transactions.decisions import read_decision

            b_decision = read_decision(store, internal)
            auth = store.read_json(internal, "portrait/authorization.json")
            assert auth["attempt_id"] == "a2"
            assert auth["decision_id"] == b_decision.decision_id
            b_portrait = store.read_artifact(internal, "portrait/processed.jpg")

        # Let A's portrait finish: it must be rejected as stale and must NOT overwrite B.
        release_portrait.set()
        t1.join(timeout=15)
        assert portrait_a_status.get("status") == 409  # STALE_PORTRAIT

        with TestClient(app) as c3:
            cookies3 = dict(cookies_holder)
            internal = _internal_tx_id(c3, None)
            store = c3.app.state.transaction_store
            auth = store.read_json(internal, "portrait/authorization.json")
            assert auth["attempt_id"] == "a2"  # still references B
            assert store.read_artifact(internal, "portrait/processed.jpg") == b_portrait  # B intact
            # A's candidate must have been discarded.
            stale_candidates = list(store.transaction_dir(internal).glob("portrait/candidates/*"))
            if stale_candidates:
                raise AssertionError(f"stale candidate left behind: {stale_candidates}")
            bh3 = _browser_headers(cookies3["lp_session"], cookies3["lp_csrf"])
            assert c3.get("/api/v1/browser/portrait", headers=bh3).status_code == 200
            # Submit sends B's portrait (callback Base64 decodes to B's processed bytes).
            submit = c3.post("/api/v1/browser/submit", headers=bh3)
            assert submit.status_code == 200, submit.text
            payload = json.loads(received["body"])
            decoded = base64.b64decode(payload["processed_jpeg_base64"])
            assert decoded == b_portrait
            assert (
                c3.get(
                    "/api/v1/integration/transactions/ext-123/status?source=D365",
                    headers=_dev_headers(),
                ).json()["status"]
                == "COMPLETED"
            )
    finally:
        PortraitProcessor.process = original  # type: ignore[method-assign]
        server.shutdown()


def test_portrait_race_stale_finishes_before_new_pass(tmp_path) -> None:
    """A portrait finishing after a new capture (before any new PASS) leaves no authorization."""
    import threading as _th

    from app.portrait import PortraitProcessor

    original = PortraitProcessor.process
    portrait_started = _th.Event()
    release_portrait = _th.Event()
    portrait_calls: list[int] = []

    async def delayed_process(
        self, source, transaction_id, *, face_box_normalized=None, output_relative_path=None
    ):
        portrait_calls.append(1)
        if len(portrait_calls) == 1:
            portrait_started.set()
            release_portrait.wait(timeout=15)
        return await original(
            self,
            source,
            transaction_id,
            face_box_normalized=face_box_normalized,
            output_relative_path=output_relative_path,
        )

    PortraitProcessor.process = delayed_process  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        cookies_holder: dict[str, str] = {}
        portrait_a_status: dict[str, int] = {}

        def attempt_a_portrait() -> None:
            with TestClient(app) as c:
                cookies = _active_cookies(c)
                cookies_holder.update(cookies)
                bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
                _capture(c, cookies, "a1", _jpeg_bytes())
                assert c.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"]
                portrait_a_status["status"] = c.post(
                    "/api/v1/browser/portrait", headers=bh
                ).status_code

        t1 = _th.Thread(target=attempt_a_portrait)
        t1.start()
        assert portrait_started.wait(timeout=10)

        # Upload B (invalidates A's PASS/portrait) but do NOT run liveness for B yet.
        with TestClient(app) as c2:
            cookies2 = dict(cookies_holder)
            _capture(c2, cookies2, "a2", _jpeg_bytes(64, 64))
            internal = _internal_tx_id(c2, None)
            assert (
                c2.app.state.transaction_store.artifact_exists(
                    internal, "portrait/authorization.json"
                )
                is False
            )

        # A finishes -> stale -> no portrait authorization.
        release_portrait.set()
        t1.join(timeout=15)
        assert portrait_a_status.get("status") == 409

        with TestClient(app) as c3:
            cookies3 = dict(cookies_holder)
            store = c3.app.state.transaction_store
            assert store.artifact_exists(internal, "portrait/authorization.json") is False
            assert store.artifact_exists(internal, "portrait/processed.jpg") is False
            bh3 = _browser_headers(cookies3["lp_session"], cookies3["lp_csrf"])
            assert c3.get("/api/v1/browser/portrait", headers=bh3).status_code == 404
            assert c3.post("/api/v1/browser/submit", headers=bh3).status_code == 412
    finally:
        PortraitProcessor.process = original  # type: ignore[method-assign]


# ------------------------------------------------------- claim recovery / single-flight tests


def _write_claim(app, tx: str, identity: str, prefix: str, started_at_iso: str) -> None:
    store: TransactionFileStore = app.state.transaction_store
    store.write_json(
        tx,
        liveness.claim_path_for(identity, prefix),
        {"identity": identity, "status": "IN_PROGRESS", "started_at": started_at_iso},
    )


def _current_identity(app, internal: str) -> str:
    store: TransactionFileStore = app.state.transaction_store
    key = liveness.current_capture_key(store, internal)
    assert key is not None
    return liveness.liveness_identity(key["attempt_id"], key["selected_sha256"])


def test_portrait_stale_does_not_mutate_newer_status(tmp_path) -> None:
    import threading as _th

    from app.portrait import PortraitProcessor

    original = PortraitProcessor.process
    started = _th.Event()
    release = _th.Event()

    async def delayed(
        self, source, transaction_id, *, face_box_normalized=None, output_relative_path=None
    ):
        started.set()
        release.wait(timeout=15)
        return await original(
            self,
            source,
            transaction_id,
            face_box_normalized=face_box_normalized,
            output_relative_path=output_relative_path,
        )

    PortraitProcessor.process = delayed  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        cookies_holder: dict[str, str] = {}
        status_holder: dict[str, int] = {}

        def a_portrait() -> None:
            with TestClient(app) as c:
                cookies = _active_cookies(c)
                cookies_holder.update(cookies)
                bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
                _capture(c, cookies, "a1", _jpeg_bytes())
                assert c.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"]
                status_holder["status"] = c.post("/api/v1/browser/portrait", headers=bh).status_code

        t1 = _th.Thread(target=a_portrait)
        t1.start()
        assert started.wait(timeout=10)

        with TestClient(app) as c2:
            cookies2 = dict(cookies_holder)
            _capture(c2, cookies2, "a2", _jpeg_bytes(64, 64))
            bh2 = _browser_headers(cookies2["lp_session"], cookies2["lp_csrf"])
            assert c2.post("/api/v1/browser/liveness", headers=bh2).json()["portrait_allowed"]
            internal = _internal_tx_id(c2, None)
            before = c2.app.state.transaction_store.read_transaction_json(internal)["status"]
            assert before == "DECISION_READY"  # B has a PASS, no portrait yet

        release.set()
        t1.join(timeout=15)
        assert status_holder.get("status") == 409  # stale

        with TestClient(app) as c3:
            store = c3.app.state.transaction_store
            internal = _internal_tx_id(c3, None)
            # Stale A completion MUST NOT have mutated B's transaction state.
            after = store.read_transaction_json(internal)["status"]
            assert after == before
    finally:
        PortraitProcessor.process = original  # type: ignore[method-assign]


def test_portrait_concurrent_single_execution(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from app.portrait import PortraitProcessor

    original = PortraitProcessor.process
    calls: list[int] = []

    async def slow(
        self, source, transaction_id, *, face_box_normalized=None, output_relative_path=None
    ):
        calls.append(1)
        await asyncio.sleep(0.3)
        return await original(
            self,
            source,
            transaction_id,
            face_box_normalized=face_box_normalized,
            output_relative_path=output_relative_path,
        )

    PortraitProcessor.process = slow  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            _capture(client, cookies, "p1", _jpeg_bytes())
            assert client.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"]
            session_cookie = cookies["lp_session"]
            csrf = cookies["lp_csrf"]

            def call() -> int:
                with TestClient(app) as c:
                    return c.post(
                        "/api/v1/browser/portrait", headers=_browser_headers(session_cookie, csrf)
                    ).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(lambda _: call(), range(2)))
            assert all(s in (200, 202) for s in statuses)
        assert len(calls) == 1  # exactly one PortraitProcessor execution
    finally:
        PortraitProcessor.process = original  # type: ignore[method-assign]


def test_portrait_stale_claim_recovers(tmp_path) -> None:
    from app.portrait import PortraitProcessor

    original = PortraitProcessor.process
    calls: list[int] = []

    async def counting(
        self, source, transaction_id, *, face_box_normalized=None, output_relative_path=None
    ):
        calls.append(1)
        return await original(
            self,
            source,
            transaction_id,
            face_box_normalized=face_box_normalized,
            output_relative_path=output_relative_path,
        )

    PortraitProcessor.process = counting  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            _capture(client, cookies, "r1", _jpeg_bytes())
            assert client.post("/api/v1/browser/liveness", headers=bh).json()["portrait_allowed"]
            internal = _internal_tx_id(client, None)
            identity = _current_identity(app, internal)
            # Backdate a stale portrait claim: it must be recovered and the portrait processed.
            stale = (
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1000)
            ).isoformat()
            _write_claim(app, internal, identity, liveness.PORTRAIT_CLAIM_PREFIX, stale)
            res = client.post("/api/v1/browser/portrait", headers=bh)
            assert res.status_code == 200, res.text
            assert client.get("/api/v1/browser/portrait", headers=bh).status_code == 200
        assert len(calls) == 1
    finally:
        PortraitProcessor.process = original  # type: ignore[method-assign]


def test_liveness_stale_claim_recovers(tmp_path) -> None:
    from app.experiments.vlm import VlmEvaluationService

    original = VlmEvaluationService.evaluate
    calls: list[int] = []

    async def counting(self, request):
        calls.append(1)
        return await original(self, request)

    VlmEvaluationService.evaluate = counting  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            _capture(client, cookies, "r2", _jpeg_bytes())
            internal = _internal_tx_id(client, None)
            identity = _current_identity(app, internal)
            stale = (
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1000)
            ).isoformat()
            _write_claim(app, internal, identity, liveness.EVALUATION_CLAIM_PREFIX, stale)
            res = client.post("/api/v1/browser/liveness", headers=bh)
            assert res.status_code == 200, res.text
            assert res.json()["portrait_allowed"] is True
        assert len(calls) == 1
    finally:
        VlmEvaluationService.evaluate = original  # type: ignore[method-assign]


def test_active_claims_do_not_duplicate_work(tmp_path) -> None:
    from app.experiments.vlm import VlmEvaluationService
    from app.portrait import PortraitProcessor

    eval_original = VlmEvaluationService.evaluate
    portrait_original = PortraitProcessor.process
    eval_calls: list[int] = []
    portrait_calls: list[int] = []

    async def count_eval(self, request):
        eval_calls.append(1)
        return await eval_original(self, request)

    async def count_portrait(
        self, source, transaction_id, *, face_box_normalized=None, output_relative_path=None
    ):
        portrait_calls.append(1)
        return await portrait_original(
            self,
            source,
            transaction_id,
            face_box_normalized=face_box_normalized,
            output_relative_path=output_relative_path,
        )

    VlmEvaluationService.evaluate = count_eval  # type: ignore[method-assign]
    PortraitProcessor.process = count_portrait  # type: ignore[method-assign]
    try:
        app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            _capture(client, cookies, "a3", _jpeg_bytes())
            internal = _internal_tx_id(client, None)
            identity = _current_identity(app, internal)
            fresh = datetime.datetime.now(datetime.UTC).isoformat()
            # Active (non-stale) claims must yield LIVENESS_IN_PROGRESS / PORTRAIT_IN_PROGRESS
            # and never trigger duplicate provider/portrait work.
            _write_claim(app, internal, identity, liveness.EVALUATION_CLAIM_PREFIX, fresh)
            res = client.post("/api/v1/browser/liveness", headers=bh)
            assert res.status_code == 202
            assert res.json()["error"]["code"] == "LIVENESS_IN_PROGRESS"

            # Clean the eval claim, run liveness, then plant an active portrait claim.
            store: TransactionFileStore = app.state.transaction_store
            store.remove_artifact(
                internal, liveness.claim_path_for(identity, liveness.EVALUATION_CLAIM_PREFIX)
            )
            assert client.post("/api/v1/browser/liveness", headers=bh).status_code == 200
            _write_claim(app, internal, identity, liveness.PORTRAIT_CLAIM_PREFIX, fresh)
            res = client.post("/api/v1/browser/portrait", headers=bh)
            assert res.status_code == 202
            assert res.json()["error"]["code"] == "PORTRAIT_IN_PROGRESS"
        assert len(eval_calls) == 1
        assert len(portrait_calls) == 0  # the active portrait claim blocked processing
    finally:
        VlmEvaluationService.evaluate = eval_original  # type: ignore[method-assign]
        PortraitProcessor.process = portrait_original  # type: ignore[method-assign]


# ----------------------------------------------- single-person enforcement (pre-M6)
def test_subject_count_live_one_pass_and_portrait(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "PASS"
        assert body["portrait_allowed"] is True
        assert body["reason_codes"] == []
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 200


def test_subject_count_live_multiple_retry_no_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False
        assert body["reason_codes"] == ["MULTIPLE_FACES"]
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        decision = read_decision(store, internal)
        assert decision is not None and decision.outcome.value == "RETRY"
        assert decision.metadata.get("subject_count") == "MULTIPLE"


def test_subject_count_live_uncertain_retry_no_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_subject_uncertain")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False


def test_subject_count_live_zero_retry_no_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_zero")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False
        assert body["reason_codes"] == ["NO_FACE"]


def test_subject_count_missing_schema_failure_fail_closed(tmp_path) -> None:
    # The "schema" mock behavior returns provider output that does not match the schema
    # (missing/invalid subject_count) -> schema failure -> fail closed, no PASS.
    app = _liveness_app(tmp_path, vlm_mock_behavior="schema")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 502
        assert res.json()["error"]["code"] == "LIVENESS_UNAVAILABLE"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        decision = read_decision(store, internal)
        assert decision is None or decision.outcome.value != "PASS"
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412


def test_subject_count_screen_replay_one_still_fail(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="screen_replay")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.json()["outcome"] == "FAIL"
        assert res.json()["portrait_allowed"] is False


def test_subject_count_print_attack_one_still_fail(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="print")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.json()["outcome"] == "FAIL"
        assert res.json()["portrait_allowed"] is False


def test_subject_count_multiple_never_creates_decision_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "a1")
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        from app.transactions.decisions import read_decision

        decision = read_decision(store, internal)
        assert decision is not None and decision.outcome.value == "RETRY"
        # has_current_canonical_pass must be false for the MULTIPLE result.
        assert liveness.has_current_canonical_pass(store, internal) is False


def test_subject_count_multiple_persisted_and_reused_idempotently(tmp_path, monkeypatch) -> None:
    from app.experiments.vlm import VlmEvaluationService

    calls: list[int] = [0]
    original = VlmEvaluationService.evaluate

    async def counting_evaluate(self, request):
        calls[0] += 1
        return await original(self, request)

    monkeypatch.setattr(VlmEvaluationService, "evaluate", counting_evaluate)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "m1")
        assert res.json()["outcome"] == "RETRY"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        identity = liveness.expected_liveness_identity(store, internal)
        cached = liveness.read_evaluation(store, internal, identity)
        assert cached["subject_count"] == "MULTIPLE"
        assert cached["reason_codes"] == ["MULTIPLE_FACES"]
        assert cached["attempt_id"] == "m1"
        # Repeating liveness for the SAME capture is served from the persisted record: no new
        # provider call (single-flight/idempotency preserved).
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        res2 = client.post("/api/v1/browser/liveness", headers=bh)
        assert res2.status_code == 200
        assert res2.json()["outcome"] == "RETRY"
        assert res2.json()["reason_codes"] == ["MULTIPLE_FACES"]
        assert calls[0] == 1


def test_subject_count_new_capture_invalidates_previous_one_live_pass(tmp_path) -> None:
    # A previously LIVE+ONE PASS is invalidated by a new capture, as before.
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "cap-1")
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert liveness.has_current_canonical_pass(store, internal) is True
        # Upload a NEW capture (new attempt + new image) WITHOUT running liveness: the previous
        # LIVE+ONE PASS must be invalidated/superseded (stale PASS can never authorize the new
        # capture).
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "cap-2", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(64, 64), "image/jpeg")},
            headers=bh,
        )
        assert liveness.has_current_canonical_pass(store, internal) is False
        # After liveness for the NEW capture (LIVE+ONE), a fresh current PASS exists.
        liv = client.post("/api/v1/browser/liveness", headers=bh)
        assert liv.status_code == 200
        assert liv.json()["outcome"] == "PASS"
        assert liveness.has_current_canonical_pass(store, internal) is True


def test_subject_count_multiple_blocks_browser_portrait_and_submit(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "a1")
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412
        assert client.post("/api/v1/browser/submit", headers=bh).status_code == 412


def test_subject_count_multiple_blocks_standalone_portrait(tmp_path) -> None:
    from fastapi.testclient import TestClient as _TC

    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with _TC(app) as client:
        tx_id = client.post(
            "/api/v1/transactions",
            files={"image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            data={
                "capture_config_version": "capture-v1",
                "quality_config_version": "quality-v1",
                "face_box": _FACE_BOX,
            },
        ).json()["transaction_id"]
        liv = client.post(f"/api/v1/transactions/{tx_id}/liveness")
        assert liv.status_code == 200
        assert liv.json()["outcome"] == "RETRY"
        assert liv.json()["reason_codes"] == ["MULTIPLE_FACES"]
        # Standalone portrait must be blocked after MULTIPLE even though classification is LIVE.
        portrait = client.post(f"/api/v1/transactions/{tx_id}/portrait")
        assert portrait.status_code == 500
        assert portrait.json()["error"]["code"] == "PORTRAIT_PROCESSING_FAILED"
        store: TransactionFileStore = app.state.transaction_store
        assert not store.artifact_exists(tx_id, "portrait/processed.jpg")


def test_subject_count_customer_reason_multiple_faces(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        # The safe customer-facing reason is MULTIPLE_FACES (never raw VLM/Groq output).
        assert res.json()["reason_codes"] == ["MULTIPLE_FACES"]
        assert res.json()["classification"] == "LIVE"  # not the reason


# ------------------------------------------- v1->v2 cache backward-compatibility (pre-M6)
def _write_cached_evaluation(
    store: TransactionFileStore,
    internal: str,
    *,
    attempt_id: str,
    selected_sha256: str,
    schema_version: str | None,
    prompt_version: str | None,
    subject_count: str | None,
    secondary_person_state: str | None = None,
    outcome: str = "PASS",
    classification: str | None = "LIVE",
    portrait_allowed: bool = True,
) -> None:
    identity = liveness.liveness_identity(attempt_id, selected_sha256)
    payload: dict[str, Any] = {
        "attempt_id": attempt_id,
        "selected_sha256": selected_sha256,
        "provider": "mock",
        "model": "mock-vision-v1",
        "classification": classification,
        "attack_medium": "NONE",
        "evidence_codes": [],
        "outcome": outcome,
        "portrait_allowed": portrait_allowed,
        "latency_ms": 1,
        "error": None,
        "created_at": "2020-01-01T00:00:00+00:00",
    }
    if schema_version is not None:
        payload["schema_version"] = schema_version
    if prompt_version is not None:
        payload["prompt_version"] = prompt_version
    if subject_count is not None:
        payload["subject_count"] = subject_count
    if secondary_person_state is not None:
        payload["secondary_person_state"] = secondary_person_state
    liveness.persist_evaluation(store, internal, identity, payload)


def _counting_service(monkeypatch):
    from app.experiments.vlm import VlmEvaluationService

    calls: list[int] = [0]
    original = VlmEvaluationService.evaluate

    async def counting_evaluate(self, request):
        calls[0] += 1
        return await original(self, request)

    monkeypatch.setattr(VlmEvaluationService, "evaluate", counting_evaluate)
    return calls


def test_is_current_evaluation_contract() -> None:
    assert liveness.is_current_evaluation(None) is False
    # Fail-closed error records are reusable (never authorize PASS).
    assert liveness.is_current_evaluation({"error": "PROVIDER_TIMEOUT"}) is True
    current = {
        "schema_version": "vlm-result-v3",
        "prompt_version": "vlm-passive-v3",
        "subject_count": "ONE",
        "secondary_person_state": "NONE",
    }
    assert liveness.is_current_evaluation(current) is True
    # Legacy v1/v2 (no secondary_person_state) is never current.
    assert (
        liveness.is_current_evaluation(
            {"schema_version": "vlm-result-v1", "prompt_version": "vlm-passive-v1"}
        )
        is False
    )
    assert (
        liveness.is_current_evaluation(
            {
                "schema_version": "vlm-result-v2",
                "prompt_version": "vlm-passive-v2",
                "subject_count": "ONE",
            }
        )
        is False
    )
    # Current schema but missing/unknown subject_count -> not reusable.
    assert (
        liveness.is_current_evaluation(
            {
                "schema_version": "vlm-result-v3",
                "prompt_version": "vlm-passive-v3",
                "secondary_person_state": "NONE",
            }
        )
        is False
    )
    assert (
        liveness.is_current_evaluation(
            {
                "schema_version": "vlm-result-v3",
                "prompt_version": "vlm-passive-v3",
                "subject_count": "TWO",
                "secondary_person_state": "NONE",
            }
        )
        is False
    )
    # Missing/unknown secondary_person_state -> not reusable.
    assert (
        liveness.is_current_evaluation(
            {
                "schema_version": "vlm-result-v3",
                "prompt_version": "vlm-passive-v3",
                "subject_count": "ONE",
            }
        )
        is False
    )
    assert (
        liveness.is_current_evaluation(
            {
                "schema_version": "vlm-result-v3",
                "prompt_version": "vlm-passive-v3",
                "subject_count": "ONE",
                "secondary_person_state": "MAYBE",
            }
        )
        is False
    )
    # Wrong prompt version -> not reusable.
    assert (
        liveness.is_current_evaluation(
            {
                "schema_version": "vlm-result-v3",
                "prompt_version": "vlm-passive-v1",
                "subject_count": "ONE",
                "secondary_person_state": "NONE",
            }
        )
        is False
    )


def test_legacy_v1_pass_cache_not_reused_reevaluates_once(tmp_path, monkeypatch) -> None:
    calls = _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        cap = client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "legacy-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        assert cap.status_code == 200
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        key = liveness.current_capture_key(store, internal)
        assert key is not None
        _write_cached_evaluation(
            store,
            internal,
            attempt_id=key["attempt_id"],
            selected_sha256=key["selected_sha256"],
            schema_version="vlm-result-v1",
            prompt_version="vlm-passive-v1",
            subject_count=None,
            outcome="PASS",
        )
        res = client.post("/api/v1/browser/liveness", headers=bh)
        assert res.status_code == 200, res.text
        # The legacy PASS cache was NOT reused: the current provider produced a fresh v2 result.
        assert calls[0] == 1
        identity = liveness.liveness_identity(key["attempt_id"], key["selected_sha256"])
        refreshed = liveness.read_evaluation(store, internal, identity)
        assert refreshed["schema_version"] == "vlm-result-v3"
        assert refreshed["subject_count"] == "ONE"


def test_legacy_v1_cache_reevaluated_live_one_may_pass(tmp_path, monkeypatch) -> None:
    _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "legacy-2", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        key = liveness.current_capture_key(store, internal)
        assert key is not None
        _write_cached_evaluation(
            store,
            internal,
            attempt_id=key["attempt_id"],
            selected_sha256=key["selected_sha256"],
            schema_version="vlm-result-v1",
            prompt_version="vlm-passive-v1",
            subject_count=None,
            outcome="PASS",
        )
        res = client.post("/api/v1/browser/liveness", headers=bh)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "PASS"
        assert body["portrait_allowed"] is True
        portrait = client.post("/api/v1/browser/portrait", headers=bh)
        assert portrait.status_code == 200, portrait.text


def test_legacy_v1_cache_reevaluated_live_multiple_retry_no_pass(tmp_path, monkeypatch) -> None:
    _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "legacy-3", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        key = liveness.current_capture_key(store, internal)
        assert key is not None
        _write_cached_evaluation(
            store,
            internal,
            attempt_id=key["attempt_id"],
            selected_sha256=key["selected_sha256"],
            schema_version="vlm-result-v1",
            prompt_version="vlm-passive-v1",
            subject_count=None,
            outcome="PASS",
        )
        res = client.post("/api/v1/browser/liveness", headers=bh)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False
        assert body["reason_codes"] == ["MULTIPLE_FACES"]
        assert liveness.has_current_canonical_pass(store, internal) is False
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412


def test_legacy_canonical_pass_decision_missing_subject_count_is_not_current(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "a1")
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert liveness.has_current_canonical_pass(store, internal) is True
        # Simulate a legacy canonical decision (v1): PASS metadata without subject_count/v2 schema.
        from app.transactions.decisions import build_decision, write_decision

        key = liveness.current_capture_key(store, internal)
        assert key is not None
        identity = liveness.liveness_identity(key["attempt_id"], key["selected_sha256"])
        legacy = build_decision(
            internal,
            source=liveness.LIVENESS_DECISION_SOURCE,
            version="liveness-v1",
            metadata={
                "attempt_id": key["attempt_id"],
                "selected_sha256": key["selected_sha256"],
                "liveness_identity": identity,
                "classification": "LIVE",
            },
        )
        write_decision(store, internal, legacy)
        assert liveness.has_current_canonical_pass(store, internal) is False


def test_current_v2_cache_reused_idempotently(tmp_path, monkeypatch) -> None:
    calls = _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "v2-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        first = client.post("/api/v1/browser/liveness", headers=bh)
        second = client.post("/api/v1/browser/liveness", headers=bh)
        assert first.status_code == 200 and second.status_code == 200
        assert first.json() == second.json()
        # A current v2 cache is reused: exactly one provider call.
        assert calls[0] == 1


def test_malformed_cached_subject_count_reevaluated_no_default_one(tmp_path, monkeypatch) -> None:
    calls = _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "bad-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        key = liveness.current_capture_key(store, internal)
        assert key is not None
        # Current schema/prompt but an unknown subject_count value and an old PASS outcome.
        _write_cached_evaluation(
            store,
            internal,
            attempt_id=key["attempt_id"],
            selected_sha256=key["selected_sha256"],
            schema_version="vlm-result-v3",
            prompt_version="vlm-passive-v3",
            subject_count="TWO",
            secondary_person_state="NONE",
            outcome="PASS",
        )
        res = client.post("/api/v1/browser/liveness", headers=bh)
        assert res.status_code == 200, res.text
        body = res.json()
        # Malformed cache was re-evaluated (never defaulted to ONE -> would have been PASS).
        assert calls[0] == 1
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False
        identity = liveness.liveness_identity(key["attempt_id"], key["selected_sha256"])
        refreshed = liveness.read_evaluation(store, internal, identity)
        assert refreshed["subject_count"] == "MULTIPLE"


def test_standalone_legacy_v1_cache_reevaluated(tmp_path, monkeypatch) -> None:
    calls = _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        tx_id = client.post(
            "/api/v1/transactions",
            files={"image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            data={
                "capture_config_version": "capture-v1",
                "quality_config_version": "quality-v1",
                "face_box": _FACE_BOX,
            },
        ).json()["transaction_id"]
        store: TransactionFileStore = app.state.transaction_store
        key = liveness.current_capture_key(store, tx_id)
        assert key is not None
        _write_cached_evaluation(
            store,
            tx_id,
            attempt_id=key["attempt_id"],
            selected_sha256=key["selected_sha256"],
            schema_version="vlm-result-v1",
            prompt_version="vlm-passive-v1",
            subject_count=None,
            outcome="PASS",
        )
        res = client.post(f"/api/v1/transactions/{tx_id}/liveness")
        assert res.status_code == 200, res.text
        # Legacy cache not reused: a fresh current-contract result was produced.
        assert calls[0] == 1
        assert res.json()["outcome"] == "PASS"
        identity = liveness.liveness_identity(key["attempt_id"], key["selected_sha256"])
        refreshed = liveness.read_evaluation(store, tx_id, identity)
        assert refreshed["schema_version"] == "vlm-result-v3"
        assert refreshed["subject_count"] == "ONE"


# ------------------------------- secondary_person_state (background vs interfering, pre-M6 v3)
def test_secondary_person_state_mapping_matrix() -> None:
    m = liveness.map_classification_to_outcome
    # Portrait-eligible coherent pairs.
    assert m("LIVE", "ONE", "NONE") is DecisionOutcome.PASS
    assert m("LIVE", "MULTIPLE", "BACKGROUND") is DecisionOutcome.PASS
    # Coherent but NOT eligible -> RETRY.
    assert m("LIVE", "MULTIPLE", "INTERFERING") is DecisionOutcome.RETRY
    assert m("LIVE", "MULTIPLE", "UNCERTAIN") is DecisionOutcome.RETRY
    assert m("LIVE", "UNCERTAIN", "UNCERTAIN") is DecisionOutcome.RETRY
    assert m("LIVE", "ZERO", "NONE") is DecisionOutcome.RETRY
    # Contradictory pairs -> inconsistent -> fail closed (never PASS).
    assert m("LIVE", "ONE", "BACKGROUND") is DecisionOutcome.RETRY
    assert m("LIVE", "ONE", "INTERFERING") is DecisionOutcome.RETRY
    assert m("LIVE", "MULTIPLE", "NONE") is DecisionOutcome.RETRY
    assert m("LIVE", "ZERO", "BACKGROUND") is DecisionOutcome.RETRY
    assert m("LIVE", "ZERO", "INTERFERING") is DecisionOutcome.RETRY
    assert m("LIVE", "UNCERTAIN", "BACKGROUND") is DecisionOutcome.RETRY
    assert m("LIVE", "UNCERTAIN", "NONE") is DecisionOutcome.RETRY
    # Missing/None person state -> fail closed, never PASS.
    assert m("LIVE", "ONE", None) is DecisionOutcome.RETRY
    assert m("LIVE", None, None) is DecisionOutcome.RETRY
    # Attack classifications FAIL regardless of person state (even inconsistent).
    assert m("SCREEN_REPLAY", "MULTIPLE", "BACKGROUND") is DecisionOutcome.FAIL
    assert m("SCREEN_REPLAY", "ONE", "BACKGROUND") is DecisionOutcome.FAIL
    assert m("PRINT_ATTACK", "MULTIPLE", "NONE") is DecisionOutcome.FAIL
    assert m("UNCERTAIN", "ONE", "NONE") is DecisionOutcome.RETRY
    # Coherence helper.
    assert liveness.is_person_state_consistent("MULTIPLE", "BACKGROUND") is True
    assert liveness.is_person_state_consistent("ZERO", "NONE") is True
    assert liveness.is_person_state_consistent("ONE", "BACKGROUND") is False
    assert liveness.is_person_state_consistent("MULTIPLE", "NONE") is False
    # Reasons: interfering -> MULTIPLE_FACES; zero -> NO_FACE; background -> none.
    assert liveness.interference_reasons("MULTIPLE", "INTERFERING") == ["MULTIPLE_FACES"]
    assert liveness.interference_reasons("ZERO", "NONE") == ["NO_FACE"]
    assert liveness.interference_reasons("MULTIPLE", "BACKGROUND") == []


def test_secondary_live_multiple_background_pass_and_portrait(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple_background")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "PASS"
        assert body["portrait_allowed"] is True
        # A distant/background second person must NOT produce a MULTIPLE_FACES retry.
        assert body["reason_codes"] == []
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert liveness.has_current_canonical_pass(store, internal) is True
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 200


def test_secondary_live_multiple_interfering_retry_multiple_faces(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200
        body = res.json()
        assert body["outcome"] == "RETRY"
        assert body["reason_codes"] == ["MULTIPLE_FACES"]
        assert body["portrait_allowed"] is False
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412


def test_secondary_live_multiple_uncertain_retry(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple_uncertain")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False


def test_secondary_attack_still_fails_regardless_of_person_state(tmp_path) -> None:
    # SCREEN_REPLAY/PRINT_ATTACK FAIL regardless of secondary_person_state.
    for behavior in ("screen_replay", "print"):
        sub = tmp_path / behavior
        sub.mkdir(parents=True, exist_ok=True)
        app = _liveness_app(sub, vlm_mock_behavior=behavior)
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            res = _capture_and_liveness(client, cookies, "a1")
            assert res.json()["outcome"] == "FAIL"
            assert res.json()["portrait_allowed"] is False
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412


def test_secondary_current_background_cache_reused_idempotently(tmp_path, monkeypatch) -> None:
    calls = _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple_background")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "bg-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        first = client.post("/api/v1/browser/liveness", headers=bh)
        second = client.post("/api/v1/browser/liveness", headers=bh)
        assert first.status_code == 200 and second.status_code == 200
        assert first.json() == second.json()
        assert first.json()["outcome"] == "PASS"
        assert calls[0] == 1  # current v3 BACKGROUND cache reused
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        identity = liveness.expected_liveness_identity(store, internal)
        cached = liveness.read_evaluation(store, internal, identity)
        assert cached["secondary_person_state"] == "BACKGROUND"
        assert cached["subject_count"] == "MULTIPLE"


def test_secondary_legacy_cache_missing_state_not_reused_as_pass(tmp_path, monkeypatch) -> None:
    # v2 cache (subject_count ONE, no secondary_person_state) must not authorize PASS.
    calls = _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "v2-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        key = liveness.current_capture_key(store, internal)
        assert key is not None
        _write_cached_evaluation(
            store,
            internal,
            attempt_id=key["attempt_id"],
            selected_sha256=key["selected_sha256"],
            schema_version="vlm-result-v2",
            prompt_version="vlm-passive-v2",
            subject_count="ONE",
            secondary_person_state=None,
            outcome="PASS",
        )
        res = client.post("/api/v1/browser/liveness", headers=bh)
        assert res.status_code == 200, res.text
        assert calls[0] == 1  # re-evaluated under the current contract
        identity = liveness.expected_liveness_identity(store, internal)
        refreshed = liveness.read_evaluation(store, internal, identity)
        assert refreshed["schema_version"] == "vlm-result-v3"
        assert refreshed["secondary_person_state"] in {"NONE", "BACKGROUND"}


def test_secondary_standalone_portrait_background_allowed_interfering_blocked(tmp_path) -> None:
    for behavior, expected_status in (
        ("live_multiple_background", 200),
        ("live_multiple", 500),
    ):
        sub = tmp_path / behavior
        sub.mkdir(parents=True, exist_ok=True)
        app = _liveness_app(sub, vlm_mock_behavior=behavior)
        with TestClient(app) as client:
            tx_id = client.post(
                "/api/v1/transactions",
                files={"image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
                data={
                    "capture_config_version": "capture-v1",
                    "quality_config_version": "quality-v1",
                    "face_box": _FACE_BOX,
                },
            ).json()["transaction_id"]
            liv = client.post(f"/api/v1/transactions/{tx_id}/liveness")
            assert liv.status_code == 200
            portrait = client.post(f"/api/v1/transactions/{tx_id}/portrait")
            assert portrait.status_code == expected_status, (behavior, portrait.text)


# ---------------------------- person-state consistency / parity at every boundary (pre-M6 v3)
def _persist_vlm_result(
    store: TransactionFileStore,
    tx_id: str,
    classification: str,
    subject_count: str,
    secondary_person_state: str,
) -> None:
    import json as _json

    from app.transactions import ArtifactType

    store.write_artifact(
        tx_id,
        ArtifactType.VLM_RESULT,
        _json.dumps(
            {
                "provider": "mock",
                "model": "mock-vision-v1",
                "classification": classification,
                "attack_medium": "NONE",
                "self_reported_confidence": 0.9,
                "evidence_codes": [],
                "subject_count": subject_count,
                "secondary_person_state": secondary_person_state,
                "latency_ms": 1,
                "request_id": "r" * 32,
            }
        ).encode(),
        content_type="application/json",
    )


def test_secondary_inconsistent_one_background_retry_no_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_one_background")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert liveness.has_current_canonical_pass(store, internal) is False
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412


def test_secondary_inconsistent_multiple_none_retry_no_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_multiple_none")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        body = res.json()
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False


def test_secondary_inconsistent_uncertain_background_retry_no_pass(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_uncertain_background")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        res = _capture_and_liveness(client, cookies, "a1")
        body = res.json()
        assert body["outcome"] == "RETRY"
        assert body["portrait_allowed"] is False


def test_secondary_zero_none_never_pass_browser_and_standalone(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live_zero")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "a1")
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert liveness.has_current_canonical_pass(store, internal) is False
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 412
    # Standalone path with a persisted LIVE + ZERO + NONE result is likewise blocked.
    sub = tmp_path / "standalone"
    sub.mkdir()
    app2 = _liveness_app(sub, vlm_mock_behavior="live")
    with TestClient(app2) as client:
        tx_id = client.post(
            "/api/v1/transactions",
            files={"image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            data={
                "capture_config_version": "capture-v1",
                "quality_config_version": "quality-v1",
                "face_box": _FACE_BOX,
            },
        ).json()["transaction_id"]
        _persist_vlm_result(client.app.state.transaction_store, tx_id, "LIVE", "ZERO", "NONE")
        portrait = client.post(f"/api/v1/transactions/{tx_id}/portrait")
        assert portrait.status_code == 500
        assert portrait.json()["error"]["code"] == "PORTRAIT_PROCESSING_FAILED"


def test_secondary_canonical_metadata_requires_coherent_pair(tmp_path) -> None:
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    from app.transactions.decisions import build_decision, write_decision

    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "a1")
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        key = liveness.current_capture_key(store, internal)
        assert key is not None
        identity = liveness.liveness_identity(key["attempt_id"], key["selected_sha256"])

        def decide(sc: str, sps: str, outcome: str = "PASS"):
            return build_decision(
                internal,
                source=liveness.LIVENESS_DECISION_SOURCE,
                version=liveness.LIVENESS_DECISION_VERSION,
                metadata={
                    "attempt_id": key["attempt_id"],
                    "selected_sha256": key["selected_sha256"],
                    "liveness_identity": identity,
                    "classification": "LIVE",
                    "subject_count": sc,
                    "secondary_person_state": sps,
                    "schema_version": liveness.VLM_SCHEMA_VERSION,
                },
            )

        # Coherent eligible pairs are current.
        write_decision(store, internal, decide("ONE", "NONE"))
        assert liveness.has_current_canonical_pass(store, internal) is True
        write_decision(store, internal, decide("MULTIPLE", "BACKGROUND"))
        assert liveness.has_current_canonical_pass(store, internal) is True
        # Coherent but not eligible.
        write_decision(store, internal, decide("ZERO", "NONE"))
        assert liveness.has_current_canonical_pass(store, internal) is False
        write_decision(store, internal, decide("MULTIPLE", "INTERFERING"))
        assert liveness.has_current_canonical_pass(store, internal) is False
        # Contradictory pairs.
        write_decision(store, internal, decide("ONE", "BACKGROUND"))
        assert liveness.has_current_canonical_pass(store, internal) is False
        write_decision(store, internal, decide("MULTIPLE", "NONE"))
        assert liveness.has_current_canonical_pass(store, internal) is False


def test_secondary_standalone_portrait_uses_same_eligibility_rule(tmp_path) -> None:
    cases = [
        ("LIVE", "ONE", "NONE", 200),
        ("LIVE", "MULTIPLE", "BACKGROUND", 200),
        ("LIVE", "MULTIPLE", "INTERFERING", 500),
        ("LIVE", "ONE", "BACKGROUND", 500),  # inconsistent
        ("LIVE", "MULTIPLE", "NONE", 500),  # inconsistent
        ("LIVE", "ZERO", "NONE", 500),
        ("SCREEN_REPLAY", "ONE", "NONE", 500),
    ]
    for index, (cls, sc, sps, expected) in enumerate(cases):
        sub = tmp_path / f"case{index}"
        sub.mkdir()
        app = _liveness_app(sub, vlm_mock_behavior="live")
        with TestClient(app) as client:
            tx_id = client.post(
                "/api/v1/transactions",
                files={"image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
                data={
                    "capture_config_version": "capture-v1",
                    "quality_config_version": "quality-v1",
                    "face_box": _FACE_BOX,
                },
            ).json()["transaction_id"]
            _persist_vlm_result(client.app.state.transaction_store, tx_id, cls, sc, sps)
            portrait = client.post(f"/api/v1/transactions/{tx_id}/portrait")
            assert portrait.status_code == expected, (cls, sc, sps, portrait.text)


def test_secondary_inconsistent_v3_cache_not_reused(tmp_path, monkeypatch) -> None:
    calls = _counting_service(monkeypatch)
    app = _liveness_app(tmp_path, vlm_mock_behavior="live")
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        client.post(
            "/api/v1/browser/capture",
            data={"attempt_id": "inc-1", "face_box": _FACE_BOX},
            files={"selected_image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=bh,
        )
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        key = liveness.current_capture_key(store, internal)
        assert key is not None
        # Contradictory current-schema cache with outcome PASS: must NOT be reused as PASS.
        _write_cached_evaluation(
            store,
            internal,
            attempt_id=key["attempt_id"],
            selected_sha256=key["selected_sha256"],
            schema_version="vlm-result-v3",
            prompt_version="vlm-passive-v3",
            subject_count="ONE",
            secondary_person_state="BACKGROUND",
            outcome="PASS",
        )
        res = client.post("/api/v1/browser/liveness", headers=bh)
        assert res.status_code == 200, res.text
        assert calls[0] == 1  # inconsistent cache -> re-evaluated once
        identity = liveness.expected_liveness_identity(store, internal)
        refreshed = liveness.read_evaluation(store, internal, identity)
        # The refreshed record is the coherent fresh one (mock live -> ONE+NONE), not the bad cache.
        assert refreshed["subject_count"] == "ONE"
        assert refreshed["secondary_person_state"] == "NONE"
        assert res.json()["outcome"] == "PASS"


# -------------------------------- internal vs external transaction IDs (pre-M6)
def test_launch_preserves_external_id_and_uses_new_internal_id(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        body = _launch(client)
        # External consumer-supplied ID is preserved verbatim in the API response.
        assert body["transaction_id"] == "ext-123"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        # Internal LivePhoto ID uses the new LP-<UTC timestamp>-<random> format.
        assert INTERNAL_TRANSACTION_ID_PATTERN.fullmatch(internal)
        assert store.transaction_exists(internal)
        metadata = store.read_transaction_json(internal)
        assert metadata["transaction_id"] == internal
        assert metadata["external_transaction_id"] == "ext-123"
        # The external ID is still exposed unchanged (idempotent reissue uses the same internal id).
        assert external_key_hash("D365", "ext-123") is not None


def test_full_submit_flow_internal_id_is_new_format(tmp_path) -> None:
    received: dict[str, Any] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            received["body"] = self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"redirect_url": "http://localhost:3001/complete"}')

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = dict(
            D365,
            **{
                "callback": {
                    "url": f"http://127.0.0.1:{port}/cb",
                    "auth_type": "none",
                    "secret_env": "",
                }
            },
        )
        app = _make_app(
            tmp_path, consumers=[profile], vlm_provider="mock", vlm_mock_behavior="live"
        )
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            internal = _internal_tx_id(client, None)
            assert INTERNAL_TRANSACTION_ID_PATTERN.fullmatch(internal)
            bh = _live_portrait(client, cookies)
            res = client.post("/api/v1/browser/submit", headers=bh)
            assert res.status_code == 200, res.text
            assert res.json()["redirect_url"] == "http://localhost:3001/complete"
            assert received["body"]  # callback delivered unchanged
    finally:
        server.shutdown()


# --------------------------------- portrait structural-quality failure (pre-M6)
class _CorruptedFaceSegmentation:
    """Raw matte with the primary face/head left side missing (confirmed failure geometry)."""

    @property
    def info(self) -> dict[str, str]:
        return {"name": "corrupted-face-test", "backend": "test", "sha256": "fake"}

    def predict_alpha(self, image):
        import numpy as np
        from PIL import Image  # noqa: F401

        width, height = image.size
        alpha = np.zeros((height, width), dtype=np.float32)
        yy, xx = np.mgrid[0:height, 0:width]
        cx = 0.5 * width
        right = xx >= cx - 0.03 * width
        head = (
            ((xx - cx) / (0.20 * width)) ** 2 + ((yy - 0.30 * height) / (0.16 * height)) ** 2 <= 1
        ) & right
        alpha[head] = 0.95
        return alpha


def test_browser_portrait_quality_failure_is_retryable(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        # Override AFTER startup (lifespan sets the fake segmentation for provider == "fake").
        app.state.portrait_segmentation = _CorruptedFaceSegmentation()
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "a1")  # LIVE -> canonical PASS
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        res = client.post(
            "/api/v1/browser/portrait",
            data={"face_box": "0.35,0.19,0.30,0.22"},
            headers=bh,
        )
        assert res.status_code == 422, res.text
        assert res.json()["error"]["code"] == "PORTRAIT_QUALITY_FAILED"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        # No corrupted portrait is promoted; the transaction is NOT a technical error (retryable).
        assert not store.artifact_exists(internal, "portrait/processed.jpg")
        assert store.read_transaction_json(internal)["status"] != "TECHNICAL_ERROR"
        assert store.read_transaction_json(internal)["status"] not in {
            "COMPLETED",
            "ATTEMPT_LIMIT_EXCEEDED",
            "FAILED",
        }


# ------------------------- face box required + bound to current capture (pre-M6)
def test_browser_portrait_missing_face_box_is_retryable(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        # Capture deliberately without a face box.
        res = _capture_and_liveness(client, cookies, "a1", face_box="")
        assert res.status_code == 200 and res.json()["outcome"] == "PASS"
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        portrait = client.post("/api/v1/browser/portrait", headers=bh)
        assert portrait.status_code == 422, portrait.text
        assert portrait.json()["error"]["code"] == "PORTRAIT_QUALITY_FAILED"
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        assert not store.artifact_exists(internal, "portrait/processed.jpg")
        assert store.read_transaction_json(internal)["status"] != "TECHNICAL_ERROR"


def test_browser_portrait_malformed_face_box_is_blocked(tmp_path) -> None:
    for bad in ("0.9,0.2,0.3,0.3", "0.5,0.5,0.01,0.4", "nan,0.2,0.3,0.4", "1,2,3"):
        sub = tmp_path / bad.replace(",", "_").replace(".", "")
        sub.mkdir(parents=True, exist_ok=True)
        app = _liveness_app(sub)
        with TestClient(app) as client:
            cookies = _active_cookies(client)
            res = _capture_and_liveness(client, cookies, "a1", face_box=bad)
            assert res.status_code == 200 and res.json()["outcome"] == "PASS"
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            portrait = client.post("/api/v1/browser/portrait", headers=bh)
            assert portrait.status_code == 422, (bad, portrait.text)
            assert portrait.json()["error"]["code"] == "PORTRAIT_QUALITY_FAILED"


def test_browser_stale_face_box_not_reused_after_new_capture(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
        # Capture A WITH a valid box -> PASS.
        res_a = _capture_and_liveness(client, cookies, "cap-A", face_box=_FACE_BOX)
        assert res_a.json()["outcome"] == "PASS"
        # Capture B (new capture) WITHOUT a box -> PASS, but B's box is absent.
        res_b = _capture_and_liveness(
            client, cookies, "cap-B", jpeg=_jpeg_bytes(64, 64), face_box=""
        )
        assert res_b.json()["outcome"] == "PASS"
        # Portrait must NOT reuse capture A's stale box: B has no box -> retryable failure.
        portrait = client.post("/api/v1/browser/portrait", headers=bh)
        assert portrait.status_code == 422, portrait.text
        assert portrait.json()["error"]["code"] == "PORTRAIT_QUALITY_FAILED"


def test_browser_face_box_persisted_in_current_capture_metadata(tmp_path) -> None:
    app = _liveness_app(tmp_path)
    with TestClient(app) as client:
        cookies = _active_cookies(client)
        _capture_and_liveness(client, cookies, "a1", face_box=_FACE_BOX)
        store: TransactionFileStore = app.state.transaction_store
        internal = _internal_tx_id(client, None)
        meta = store.read_json(internal, "capture/capture.json")
        assert meta["face_box"] == [0.35, 0.28, 0.30, 0.26]
        assert liveness.current_capture_face_box(store, internal) == (0.35, 0.28, 0.30, 0.26)
