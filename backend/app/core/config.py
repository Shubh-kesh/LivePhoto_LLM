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

    # ---- Transaction file storage (M5.7 §7, §79-81). Filesystem-based; no object storage. ----
    file_storage_root: str = "./local-data/file-storage"
    file_storage_transactions_dir: str = "transactions"

    # ---- Portrait processing (M5.7 §37-40, §110). ----
    portrait_processing_enabled: bool = False
    portrait_background_mode: str = "solid"
    portrait_background_color: str = "#FFFFFF"
    portrait_crop_mode: str = "passport"
    portrait_output_format: str = "jpeg"
    portrait_jpeg_quality: int = 95
    portrait_model_path: str = ""
    #: Pinned SHA-256 of the provisioned portrait model asset (verified at load, M5.7 §52).
    portrait_model_sha256: str = ""
    #: Test-only segmentation provider ("fake") for deterministic CI/E2E (never in production).
    portrait_segmentation_provider: str = ""

    # --------------------------------------------------------------------------
    # M5.8 — Secure Consumer Integration.
    # --------------------------------------------------------------------------

    #: Browser-facing origin used to build public launch URLs (never the backend's own origin).
    public_livephoto_base_url: str = ""
    #: Path to the consumer-profile configuration (committed example; real profiles mounted).
    #: Relative to the backend process cwd (the backend normally runs from ``backend/``), so the
    #: committed example resolves to ``backend/config/consumers.example.json``.
    consumer_profiles_path: str = "config/consumers.example.json"

    # Launch capability tokens (M5.8 §7). Opaque, >=256-bit, hash-only persistence.
    launch_token_ttl_seconds: int = 600

    # Browser session (M5.8 §10) and session-bound CSRF (M5.8 §11).
    browser_session_ttl_seconds: int = 1800
    browser_cookie_secure: bool = True
    browser_cookie_samesite: Literal["strict", "lax", "none"] = "strict"

    # S2S authentication (M5.8 §5). "" = unconfigured (S2S endpoints refuse).
    s2s_auth_mode: Literal["", "jwt", "local_dev"] = ""
    s2s_local_dev_token: SecretStr = SecretStr("")
    s2s_jwt_issuer: str = ""
    s2s_jwt_audience: str = "livephoto"
    s2s_jwt_jwks_url: str = ""
    #: JWT claim carrying the client identity mapped to ConsumerProfile.jwt_client_ids.
    s2s_jwt_client_id_claim: str = "client_id"
    s2s_jwt_clock_skew_seconds: int = 30
    s2s_jwt_algorithms: tuple[str, ...] = ("RS256",)

    # Outbound consumer callback (M5.8 §20-22).
    callback_timeout_seconds: float = 10.0
    callback_max_retries: int = 2

    # Server-authoritative capture-attempt policy (M5.8 §15).
    capture_attempt_warning_at: int = 5
    capture_attempt_warning_again_at: int = 7
    capture_attempt_limit: int = 10

    #: Test-only canonical PASS writer; registered only when app_env in local/test/development.
    decision_test_writer_enabled: bool = False

    @field_validator(
        "capture_attempt_warning_at", "capture_attempt_warning_again_at", "capture_attempt_limit"
    )
    @classmethod
    def _validate_attempt_nonzero(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("capture attempt thresholds must be positive")
        return value

    @model_validator(mode="after")
    def _validate_attempt_order(self) -> Settings:
        if not (
            self.capture_attempt_warning_at
            < self.capture_attempt_warning_again_at
            < self.capture_attempt_limit
        ):
            raise ValueError(
                "capture attempt thresholds must satisfy warning_at < warning_again_at < limit"
            )
        return self

    @field_validator("s2s_jwt_clock_skew_seconds")
    @classmethod
    def _validate_clock_skew(cls, value: int) -> int:
        if value < 0:
            raise ValueError("S2S_JWT_CLOCK_SKEW_SECONDS must be >= 0")
        return value

    @property
    def s2s_jwks_is_local_path(self) -> bool:
        """True when JWKS is a local filesystem path (allowed only in non-uat/prod)."""
        return self.s2s_jwt_jwks_url.startswith(("/", "./", "../"))

    @model_validator(mode="after")
    def _validate_s2s_environment_gates(self) -> Settings:
        """Structural auth gates: local-dev auth and file-JWKS are impossible in uat/production.

        Mirrors the M5.6/M5.7 app_env-gating precedent but fails at boot (stronger) rather than at
        request time, so a misconfigured uat/prod deployment cannot start.
        """
        if self.app_env in ("uat", "production"):
            if self.s2s_auth_mode == "local_dev":
                raise ValueError(
                    "S2S_AUTH_MODE=local_dev is forbidden in uat/production (S2S JWT required)"
                )
            if self.s2s_auth_mode == "jwt" and not self.s2s_jwt_jwks_url:
                raise ValueError("S2S_AUTH_MODE=jwt requires S2S_JWT_JWKS_URL in uat/production")
            if self.s2s_jwks_is_local_path:
                raise ValueError("local filesystem JWKS is forbidden in uat/production")
            if self.browser_cookie_secure is not True:
                raise ValueError("browser session cookie must be Secure in uat/production")
            if self.public_livephoto_base_url:
                from urllib.parse import urlparse

                parsed = urlparse(self.public_livephoto_base_url)
                if parsed.scheme != "https" or parsed.query or parsed.fragment:
                    raise ValueError(
                        "PUBLIC_LIVEPHOTO_BASE_URL must be an https origin in uat/production"
                    )
        return self

    @field_validator("portrait_background_mode")
    @classmethod
    def _validate_portrait_background_mode(cls, value: str) -> str:
        if value not in ("solid",):
            raise ValueError(f"unsupported PORTRAIT_BACKGROUND_MODE '{value}' (only 'solid')")
        return value

    @field_validator("portrait_background_color")
    @classmethod
    def _validate_portrait_background_color(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError("PORTRAIT_BACKGROUND_COLOR must be #RRGGBB")
        return value.upper()

    @field_validator("portrait_crop_mode")
    @classmethod
    def _validate_portrait_crop_mode(cls, value: str) -> str:
        if value != "passport":
            raise ValueError("unsupported PORTRAIT_CROP_MODE (only 'passport')")
        return value

    @field_validator("portrait_output_format")
    @classmethod
    def _validate_portrait_output_format(cls, value: str) -> str:
        if value != "jpeg":
            raise ValueError("unsupported PORTRAIT_OUTPUT_FORMAT (only 'jpeg')")
        return value

    @field_validator("portrait_jpeg_quality")
    @classmethod
    def _validate_portrait_jpeg_quality(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("PORTRAIT_JPEG_QUALITY must be between 1 and 100")
        return value

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
