"""M5.8 Secure Consumer Integration tests."""

from __future__ import annotations

import base64
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
from app.factory import create_app
from app.integrations.callback import build_callback_event_id
from app.integrations.store import external_key_hash
from app.transactions.store import TransactionFileStore

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
            data={"attempt_id": "c1"},
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
        data={"attempt_id": "cap1"},
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
        app = _make_app(tmp_path, consumers=[profile])
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            # canonical PASS via dev writer
            dev = client.post("/api/v1/dev/test-decision", headers=bh)
            assert dev.status_code == 200, dev.text
            # portrait
            portrait = client.post("/api/v1/browser/portrait", headers=bh)
            assert portrait.status_code == 200, portrait.text
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
        app = _make_app(tmp_path, consumers=[profile])
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            client.post("/api/v1/dev/test-decision", headers=bh)
            client.post("/api/v1/browser/portrait", headers=bh)
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
        app = _make_app(tmp_path, consumers=[profile])
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            client.post("/api/v1/dev/test-decision", headers=bh)
            client.post("/api/v1/browser/portrait", headers=bh)
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
    # subdomain / substring / endsWith must NOT match
    assert not validate_redirect_url(
        profile, "https://consumer.example.test.evil.com/", local=False
    )
    assert not validate_redirect_url(profile, "https://evil-consumer.example.test/", local=False)
    assert not validate_redirect_url(profile, "https://consumer.example.test:8443/", local=False)
    # http disallowed outside local; userinfo/query/fragment rejected
    assert not validate_redirect_url(profile, "http://consumer.example.test/", local=False)
    assert not validate_redirect_url(profile, "https://user@consumer.example.test/", local=False)
    assert not validate_redirect_url(profile, "https://consumer.example.test/?x=1", local=False)
    assert not validate_redirect_url(profile, "https://consumer.example.test/#f", local=False)
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
        app = _make_app(tmp_path, consumers=[profile])
        with TestClient(app) as client:
            cookies = _redeem_and_capture(client)
            bh = _browser_headers(cookies["lp_session"], cookies["lp_csrf"])
            client.post("/api/v1/dev/test-decision", headers=bh)
            assert client.post("/api/v1/browser/portrait", headers=bh).status_code == 200

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
