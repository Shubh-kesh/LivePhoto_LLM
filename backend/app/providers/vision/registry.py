"""Provider registry (M4 §76).

A small explicit factory; not a plugin framework. ``mock`` is always available for tests/dev; real
providers require a configured API key + model.
"""

from __future__ import annotations

from app.core.config import Settings
from app.providers.vision.contracts import VisionProvider
from app.providers.vision.errors import VlmError, VlmErrorCode, VlmNotConfiguredError
from app.providers.vision.gemini_provider import GeminiVisionProvider
from app.providers.vision.groq_provider import GroqVisionProvider
from app.providers.vision.mock_provider import MockVisionProvider
from app.providers.vision.openrouter_provider import OpenRouterVisionProvider

REAL_PROVIDER_NAMES = ("gemini", "groq", "openrouter")


def _has_secret(value: object) -> bool:
    from pydantic import SecretStr

    return bool(value.get_secret_value()) if isinstance(value, SecretStr) else bool(value)


def get_vision_provider(settings: Settings, name: str) -> VisionProvider:
    provider = (name or "").lower()
    if provider == "mock":
        return MockVisionProvider(
            timeout_seconds=settings.vlm_timeout_seconds,
            max_retries=settings.vlm_max_retries,
        )
    if provider == "gemini":
        key = settings.gemini_api_key.get_secret_value()
        if not _has_secret(key) or not settings.gemini_model:
            raise VlmNotConfiguredError("gemini")
        return GeminiVisionProvider(
            api_key=key,
            model=settings.gemini_model,
            timeout_seconds=settings.vlm_timeout_seconds,
            max_retries=settings.vlm_max_retries,
        )
    if provider == "groq":
        key = settings.groq_api_key.get_secret_value()
        if not _has_secret(key) or not settings.groq_model:
            raise VlmNotConfiguredError("groq")
        return GroqVisionProvider(
            api_key=key,
            model=settings.groq_model,
            timeout_seconds=settings.vlm_timeout_seconds,
            max_retries=settings.vlm_max_retries,
        )
    if provider == "openrouter":
        key = settings.openrouter_api_key.get_secret_value()
        if not _has_secret(key) or not settings.openrouter_model:
            raise VlmNotConfiguredError("openrouter")
        return OpenRouterVisionProvider(
            api_key=key,
            model=settings.openrouter_model,
            timeout_seconds=settings.vlm_timeout_seconds,
            max_retries=settings.vlm_max_retries,
        )
    raise VlmError(VlmErrorCode.UNKNOWN_PROVIDER_ERROR, f"unknown VLM provider '{name}'")


def available_providers(settings: Settings) -> list[str]:
    """Providers currently configured (plus the always-available mock for dev/tests)."""
    providers: list[str] = []
    if _has_secret(settings.gemini_api_key) and settings.gemini_model:
        providers.append("gemini")
    if _has_secret(settings.groq_api_key) and settings.groq_model:
        providers.append("groq")
    if _has_secret(settings.openrouter_api_key) and settings.openrouter_model:
        providers.append("openrouter")
    providers.append("mock")
    return providers
