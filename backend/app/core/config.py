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

    # ---- VLM experiment (M4, M5.6) — disabled by default. ----
    vlm_experiment_enabled: bool = False
    # UAT local-experiment enablement: UAT experiment is available ONLY when BOTH
    # VLM_EXPERIMENT_ENABLED=true AND VLM_UAT_LOCAL_EXPERIMENT_ENABLED=true (M5.6 §12). External
    # providers remain blocked in UAT regardless.
    vlm_uat_local_experiment_enabled: bool = False
    # Structured VLM request/response/error diagnostics logging (M5.6 §27-33).
    vlm_experiment_logging_enabled: bool = False
    vlm_experiment_log_raw_model_text: bool = False

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

    # ---- Self-hosted local VLM (Gemma) provider — UAT (M5.6 §15-20). ----
    local_vlm_base_url: str = ""
    local_vlm_model: str = ""
    local_vlm_api_key: SecretStr = SecretStr("")
    local_vlm_timeout_seconds: float = 60.0
    local_vlm_max_images: int = 3
    local_vlm_verify_tls: bool = True

    @property
    def vlm_experiment_available(self) -> bool:
        """Experiment availability by environment (M5.6 §11-14).

        - local/test/development: available when ``vlm_experiment_enabled``.
        - uat: available only when ``vlm_experiment_enabled`` AND
          ``vlm_uat_local_experiment_enabled`` (local provider only).
        - production: always unavailable (hard blocked).
        """
        if not self.vlm_experiment_enabled:
            return False
        if self.app_env == "production":
            return False
        if self.app_env == "uat":
            return self.vlm_uat_local_experiment_enabled
        return True

    @property
    def local_vlm_configured(self) -> bool:
        return bool(self.local_vlm_base_url) and bool(self.local_vlm_model)

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
