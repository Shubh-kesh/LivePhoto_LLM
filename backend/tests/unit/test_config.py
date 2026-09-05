"""Configuration validation tests (M1 §54)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_settings_load() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "LivePhoto"
    assert settings.app_env == "local"
    assert settings.app_version == "0.1.0"
    assert settings.database_url == ""
    assert settings.cors_origins == ["http://localhost:5173"]


def test_cors_origins_accepts_json_list_string() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins='["http://localhost:5173", "https://bank.example.com"]',
    )
    assert settings.cors_origins == ["http://localhost:5173", "https://bank.example.com"]


def test_cors_origins_accepts_python_list() -> None:
    settings = Settings(_env_file=None, cors_origins=["http://localhost:5173"])
    assert settings.cors_origins == ["http://localhost:5173"]


def test_cors_origins_rejects_non_json_string() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins="http://localhost:5173,http://x")


def test_cors_origins_rejects_non_string_items() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins="[1, 2]")


def test_wildcard_cors_with_credentials_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=["*"], cors_allow_credentials=True)


def test_empty_cors_origins_allowed() -> None:
    settings = Settings(_env_file=None, cors_origins="")
    assert settings.cors_origins == []


def test_app_environment_types() -> None:
    assert Settings(_env_file=None, app_env="local").app_env == "local"
    assert Settings(_env_file=None, app_env="test").app_env == "test"
    assert Settings(_env_file=None, app_env="development").app_env == "development"
    assert Settings(_env_file=None, app_env="uat").app_env == "uat"
    assert Settings(_env_file=None, app_env="production").app_env == "production"
    assert Settings(_env_file=None, app_env="production").is_production is True


def test_invalid_app_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production-like")  # type: ignore[arg-type]
