"""Provider registry tests (M4 §76)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.vision import VlmError, VlmErrorCode
from app.providers.vision.local_provider import LocalVisionProvider
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


def test_local_provider_requires_configuration() -> None:
    with pytest.raises(VlmError) as exc:
        get_vision_provider(_settings(), "local")
    assert exc.value.code is VlmErrorCode.PROVIDER_NOT_CONFIGURED
    assert "local" not in available_providers(_settings())


def test_local_provider_constructed_when_configured() -> None:
    settings = _settings(
        local_vlm_base_url="http://gemma:8000/v1",
        local_vlm_model="google/gemma-3-12b-it",
    )
    provider = get_vision_provider(settings, "local")
    assert isinstance(provider, LocalVisionProvider)
    assert "local" in available_providers(settings)


def test_uat_only_lists_local_provider() -> None:
    settings = _settings(
        app_env="uat",
        local_vlm_base_url="http://gemma:8000/v1",
        local_vlm_model="google/gemma-3-12b-it",
        gemini_api_key="accidental-key",
        gemini_model="gemini-2.0-flash",
    )
    providers = available_providers(settings)
    assert providers == ["local"]
    assert "gemini" not in providers
    assert "mock" not in providers


def test_external_providers_never_listed_in_production() -> None:
    settings = _settings(
        app_env="production",
        local_vlm_base_url="http://gemma:8000/v1",
        local_vlm_model="google/gemma-3-12b-it",
        gemini_api_key="accidental-key",
        gemini_model="gemini-2.0-flash",
    )
    providers = available_providers(settings)
    assert "gemini" not in providers
    assert "local" not in providers
