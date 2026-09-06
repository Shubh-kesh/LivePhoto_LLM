"""Strongly typed application configuration (pydantic-settings).

Environment variables are the source of truth in deployed environments; a local ``.env`` file is
read for developer convenience. See ``.env.example`` at the repository root.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnvironment = Literal["local", "test", "development", "uat", "production"]
LogFormat = Literal["console", "json"]
TracesExporter = Literal["none", "console"]


class Settings(BaseSettings):
    """Application settings. Fields map 1:1 to environment variables.

    Environment names are *not* used as security authorization logic. Security properties are
    explicit settings (e.g. ``cors_allow_credentials``, ``hsts_enabled``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "LivePhoto"
    app_env: AppEnvironment = "local"
    app_version: str = "0.1.0"

    api_v1_prefix: str = "/api/v1"

    log_level: str = "INFO"
    log_format: LogFormat = "console"

    cors_origins: list[str] = ["http://localhost:5173"]
    cors_allow_credentials: bool = False

    database_url: str = ""

    otel_enabled: bool = False
    otel_service_name: str = "livephoto-backend"
    otel_traces_exporter: TracesExporter = "none"

    prometheus_enabled: bool = True
    metrics_path: str = "/metrics"

    hsts_enabled: bool = False

    # ---- VLM experiment (M4) — development-only, disabled by default. ----
    vlm_experiment_enabled: bool = False
    vlm_provider: str = ""
    vlm_timeout_seconds: float = 60.0
    vlm_max_retries: int = 1
    vlm_max_frames: int = 3
    vlm_max_single_image_bytes: int = 5 * 1024 * 1024
    vlm_max_total_image_bytes: int = 15 * 1024 * 1024
    vlm_allowed_mime_types: tuple[str, ...] = ("image/jpeg",)

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = ""
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""

    @property
    def vlm_experiment_available(self) -> bool:
        """Experiment endpoint usable only when enabled AND never in uat/production (M4 §10-11)."""
        return self.vlm_experiment_enabled and self.app_env not in ("uat", "production")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Require a structured JSON list for CORS origins.

        Avoids brittle comma/string parsing. An empty string yields an empty list.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise ValueError(
                    "CORS_ORIGINS must be a JSON array of strings, "
                    f"e.g. '[\"http://localhost:5173\"]'. Got: {value!r}"
                ) from exc
            if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                raise ValueError("CORS_ORIGINS must be a JSON array of strings")
            return parsed
        return value

    @model_validator(mode="after")
    def _reject_wildcard_with_credentials(self) -> Settings:
        if self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must not contain '*' when CORS_ALLOW_CREDENTIALS=true")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, cached after first load."""
    return Settings()
