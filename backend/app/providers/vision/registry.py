"""Provider registry (M4 §76, M5.6 §11-14, §23).

A small explicit factory; not a plugin framework. ``mock`` is always available for local/test/dev;
real external providers require a configured API key + model; the self-hosted ``local`` provider
(Gemma) requires ``LOCAL_VLM_BASE_URL`` + ``LOCAL_VLM_MODEL``.

``available_providers`` is environment-aware (M5.6 §26): it returns only providers actually
permitted in the current environment. External providers are blocked in ``uat`` and ``production``
even if keys accidentally exist; ``uat`` permits ONLY the self-hosted ``local`` provider (and only
when the UAT local-experiment flag is set via ``vlm_experiment_available``).
"""

from __future__ import annotations

from app.core.config import Settings
from app.providers.vision.contracts import VisionProvider
from app.providers.vision.errors import VlmError, VlmErrorCode, VlmNotConfiguredError
from app.providers.vision.gemini_provider import GeminiVisionProvider
from app.providers.vision.groq_provider import GroqVisionProvider
from app.providers.vision.local_provider import LocalVisionProvider
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
    if provider == "local":
        if not settings.local_vlm_configured:
            raise VlmNotConfiguredError("local")
        # Raw local-model response text is a diagnostic UAT feature: allowed only for the local
        # provider and never in production (M5.6 §33).
        log_raw = settings.vlm_experiment_log_raw_model_text and settings.app_env != "production"
        return LocalVisionProvider(
            base_url=settings.local_vlm_base_url,
            model=settings.local_vlm_model,
            api_key=settings.local_vlm_api_key.get_secret_value(),
            timeout_seconds=settings.local_vlm_timeout_seconds,
            max_images=settings.local_vlm_max_images,
            verify_tls=settings.local_vlm_verify_tls,
            max_retries=settings.vlm_max_retries,
            log_raw_text=log_raw,
        )
    raise VlmError(VlmErrorCode.UNKNOWN_PROVIDER_ERROR, f"unknown VLM provider '{name}'")


def available_providers(settings: Settings) -> list[str]:
    """Providers permitted in the current environment (M5.6 §26).

    External providers are never listed in ``uat``/``production``; ``uat`` lists only ``local``;
    ``mock`` is a local/test/dev helper only. The endpoint additionally refuses to list anything
    when the experiment is disabled (see ``vlm_experiment_available``).
    """
    providers: list[str] = []
    external_allowed = settings.app_env not in ("uat", "production")

    if external_allowed:
        if _has_secret(settings.gemini_api_key) and settings.gemini_model:
            providers.append("gemini")
        if _has_secret(settings.groq_api_key) and settings.groq_model:
            providers.append("groq")
        if _has_secret(settings.openrouter_api_key) and settings.openrouter_model:
            providers.append("openrouter")

    if settings.app_env != "production" and settings.local_vlm_configured:
        providers.append("local")

    if settings.app_env in ("local", "test", "development"):
        providers.append("mock")

    return providers
