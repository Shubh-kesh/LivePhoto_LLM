"""Consumer profiles (M5.8 §4, §6).

Backend-config consumer profiles (no DB). The committed ``consumers.example.json`` contains safe
placeholder values (``active: false``); real profiles are mounted and gitignored. Callback bearer
secrets are never stored in the profile — only the environment variable name in
``callback.secret_env``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import AppEnvironment


class ConsumerConfigError(Exception):
    """Raised when a consumer profile file is missing, unparseable or invalid."""


class CallbackConfig(BaseModel):
    url: str = ""
    auth_type: Literal["none", "bearer_env"] = "none"
    secret_env: str = ""


class RequestPolicy(BaseModel):
    ocr_required: list[bool] = Field(default_factory=lambda: [False])
    camera_configs: list[str] = Field(default_factory=lambda: ["1"])
    white_background: list[bool] = Field(default_factory=lambda: [True])
    output_formats: list[str] = Field(default_factory=lambda: ["jpeg"])


class ConsumerProfile(BaseModel):
    consumer_id: str = Field(min_length=1)
    active: bool = True
    name: str = ""
    jwt_client_ids: list[str] = Field(default_factory=list)
    callback: CallbackConfig = Field(default_factory=CallbackConfig)
    allowed_redirect_origins: list[str] = Field(default_factory=list)
    request_policy: RequestPolicy = Field(default_factory=RequestPolicy)
    max_attempts: int = 10
    watermark_spec: Any = None

    def matches_client_id(self, client_id: str) -> bool:
        return client_id in self.jwt_client_ids

    def request_policy_allows(
        self,
        *,
        ocr_required: bool,
        camera_config: str,
        white_background: bool,
        output_file_format: str,
    ) -> bool:
        return (
            ocr_required in self.request_policy.ocr_required
            and camera_config in self.request_policy.camera_configs
            and white_background in self.request_policy.white_background
            and output_file_format in self.request_policy.output_formats
        )

    def allows_redirect_origin(self, origin: str) -> bool:
        """Exact origin match only (no substring / no endsWith domain logic) — M5.8 §23."""
        return origin in self.allowed_redirect_origins

    def validate_callback_auth(self, app_env: AppEnvironment) -> None:
        """UAT/production must use ``bearer_env`` callback auth (M5.8 §21)."""
        if app_env in ("uat", "production") and self.callback.auth_type != "bearer_env":
            raise ConsumerConfigError(
                f"consumer '{self.consumer_id}' must use auth_type 'bearer_env' in {app_env}"
            )


class ConsumerRegistry:
    def __init__(self, profiles: list[ConsumerProfile]) -> None:
        self._by_id: dict[str, ConsumerProfile] = {}
        for profile in profiles:
            self._by_id[profile.consumer_id] = profile

    def get(self, consumer_id: str) -> ConsumerProfile | None:
        return self._by_id.get(consumer_id)

    def active_consumer(self, consumer_id: str) -> ConsumerProfile | None:
        profile = self.get(consumer_id)
        if profile is None or not profile.active:
            return None
        return profile

    def find_by_client_id(self, client_id: str) -> ConsumerProfile | None:
        for profile in self._by_id.values():
            if profile.matches_client_id(client_id):
                return profile
        return None


def load_consumer_profiles(path: str, app_env: AppEnvironment) -> list[ConsumerProfile]:
    """Load and validate consumer profiles from a JSON file.

    Raises ``ConsumerConfigError`` on missing/unparseable/invalid file so callers can fail closed.
    """
    config_path = Path(path)
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise ConsumerConfigError(f"cannot read consumer profiles at '{path}': {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConsumerConfigError(f"consumer profiles JSON is invalid: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("consumers"), list):
        raise ConsumerConfigError("consumer profiles must be a JSON object with a 'consumers' list")
    profiles: list[ConsumerProfile] = []
    for entry in parsed["consumers"]:
        profile = ConsumerProfile.model_validate(entry)
        profile.validate_callback_auth(app_env)
        profiles.append(profile)
    return profiles
