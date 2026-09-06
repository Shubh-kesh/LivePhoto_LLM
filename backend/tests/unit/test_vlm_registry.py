"""Provider registry tests (M4 §76)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.vision import VlmError, VlmErrorCode
from app.providers.vision.mock_provider import MockVisionProvider
from app.providers.vision.registry import available_providers, get_vision_provider


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"app_env": "test"}
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


def test_mock_always_available_without_credentials() -> None:
    settings = _settings()
    provider = get_vision_provider(settings, "mock")
    assert isinstance(provider, MockVisionProvider)
    assert "mock" in available_providers(settings)


def test_real_provider_requires_credentials() -> None:
    settings = _settings()
    with pytest.raises(VlmError) as exc:
        get_vision_provider(settings, "gemini")
    assert exc.value.code is VlmErrorCode.PROVIDER_NOT_CONFIGURED
    assert "gemini" not in available_providers(settings)


def test_unknown_provider_rejected() -> None:
    with pytest.raises(VlmError) as exc:
        get_vision_provider(_settings(), "not-a-provider")
    assert exc.value.code is VlmErrorCode.UNKNOWN_PROVIDER_ERROR


def test_configured_provider_listed() -> None:
    settings = _settings(gemini_api_key="secret", gemini_model="gemini-2.0-flash")
    assert "gemini" in available_providers(settings)
