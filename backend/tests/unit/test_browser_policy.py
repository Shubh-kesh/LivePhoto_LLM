"""Browser-support policy tests (pre-M6).

Validates loading/validation of ``config/browser-support.json``, fail-safe behaviour on malformed
config, and the safe ``/api/v1/info`` exposure of the policy.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.browser_policy import (
    BrowserPolicyConfigError,
    BrowserSupportPolicy,
    load_browser_support_policy,
)
from app.factory import create_app
from tests.conftest import make_settings

VALID_POLICY = {
    "policy_version": "browser-policy-v1",
    "browsers": {
        "chrome": {"minimum_major": 120, "enabled": True},
        "edge": {"minimum_major": 120, "enabled": True},
        "firefox": {"minimum_major": 120, "enabled": True},
        "safari": {"minimum_major": 17, "enabled": True},
        "ios_safari": {"minimum_major": 17, "enabled": True},
        "android_chrome": {"minimum_major": 120, "enabled": True},
    },
}


def _write_policy(tmp_path, payload) -> str:
    path = tmp_path / "browser-support.json"
    path.write_text(json.dumps(payload))
    return str(path)


def test_valid_policy_loads(tmp_path) -> None:
    path = _write_policy(tmp_path, VALID_POLICY)
    policy = load_browser_support_policy(path)
    assert isinstance(policy, BrowserSupportPolicy)
    assert policy.policy_version == "browser-policy-v1"
    assert policy.browsers.chrome.minimum_major == 120
    assert policy.browsers.chrome.enabled is True
    assert policy.browsers.ios_safari.minimum_major == 17


def test_malformed_json_fails_safely(tmp_path) -> None:
    path = tmp_path / "browser-support.json"
    path.write_text("{ not json !!!")
    with pytest.raises(BrowserPolicyConfigError):
        load_browser_support_policy(path)


def test_missing_file_fails_safely(tmp_path) -> None:
    with pytest.raises(BrowserPolicyConfigError):
        load_browser_support_policy(str(tmp_path / "does-not-exist.json"))


def test_non_object_root_fails_safely(tmp_path) -> None:
    path = _write_policy(tmp_path, [1, 2, 3])
    with pytest.raises(BrowserPolicyConfigError):
        load_browser_support_policy(path)


def test_missing_policy_version_is_explicit(tmp_path) -> None:
    payload = dict(VALID_POLICY)
    del payload["policy_version"]
    path = _write_policy(tmp_path, payload)
    with pytest.raises(BrowserPolicyConfigError):
        load_browser_support_policy(path)


def test_negative_and_zero_minimum_rejected(tmp_path) -> None:
    for bad in (-1, 0):
        payload = json.loads(json.dumps(VALID_POLICY))
        payload["browsers"]["chrome"]["minimum_major"] = bad
        path = _write_policy(tmp_path, payload)
        with pytest.raises(BrowserPolicyConfigError):
            load_browser_support_policy(path)


def test_unknown_browser_key_rejected(tmp_path) -> None:
    payload = json.loads(json.dumps(VALID_POLICY))
    payload["browsers"]["opera"] = {"minimum_major": 100, "enabled": True}
    path = _write_policy(tmp_path, payload)
    with pytest.raises(BrowserPolicyConfigError):
        load_browser_support_policy(path)


def test_missing_browser_family_rejected(tmp_path) -> None:
    payload = json.loads(json.dumps(VALID_POLICY))
    del payload["browsers"]["firefox"]
    path = _write_policy(tmp_path, payload)
    with pytest.raises(BrowserPolicyConfigError):
        load_browser_support_policy(path)


def test_non_boolean_enabled_rejected(tmp_path) -> None:
    payload = json.loads(json.dumps(VALID_POLICY))
    payload["browsers"]["chrome"]["enabled"] = "yes"
    path = _write_policy(tmp_path, payload)
    with pytest.raises(BrowserPolicyConfigError):
        load_browser_support_policy(path)


def test_info_returns_safe_browser_policy(tmp_path) -> None:
    settings = make_settings(browser_support_policy_path=_write_policy(tmp_path, VALID_POLICY))
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/info")
    assert response.status_code == 200
    body = response.json()
    assert body["browser_policy"]["policy_version"] == "browser-policy-v1"
    assert body["browser_policy"]["browsers"]["chrome"]["minimum_major"] == 120


def test_info_never_exposes_paths_or_secrets(tmp_path) -> None:
    settings = make_settings(browser_support_policy_path=_write_policy(tmp_path, VALID_POLICY))
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/info")
    assert response.status_code == 200
    text = response.text
    assert "browser-support.json" not in text
    assert "config" not in text.lower()
    assert "tmp" not in text
    assert "browser_policy_config_error" not in text
    assert "secret" not in text.lower()
    assert "database_url" not in text
    assert "api_key" not in text.lower()


def test_info_policy_absent_in_local_when_file_missing(tmp_path) -> None:
    settings = make_settings(
        browser_support_policy_path=str(tmp_path / "missing-browser-support.json")
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/info")
    assert response.status_code == 200
    body = response.json()
    # Missing policy is EXPLICIT (null), never silently a fabricated policy.
    assert body["browser_policy"] is None
    # local/test/dev stays bootable.
    assert client.get("/health/live").status_code == 200
