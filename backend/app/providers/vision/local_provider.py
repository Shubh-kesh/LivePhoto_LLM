"""Self-hosted local VLM provider (M5.6 §15-23, §25).

Speaks the OpenAI-compatible multimodal Chat Completions API (e.g. a local Gemma vision model
served by vLLM). Reuses the shared OpenAI-compatible transport so request building, structured
JSON output and strict ``VlmAssessment`` validation are identical to the external providers.

- The ``LOCAL_VLM_BASE_URL`` is the OpenAI-compatible base (e.g. ``http://host:8000/v1``); the
  provider calls ``POST <base>/chat/completions`` (and ``GET <base>/models`` for health).
- No fallback to any external provider: a local failure surfaces as a diagnostic provider error
  (M5.6 §25).
- Base64 exists only as a transient in-memory provider transport representation; it is never
  logged, persisted, or returned (M5.6 §21).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.providers.vision.base import run_with_retries
from app.providers.vision.contracts import (
    ProviderHealth,
    VisionProvider,
    VisionProviderCapabilities,
    VisionProviderInfo,
)
from app.providers.vision.models import (
    VisionEvaluationRequest,
    VisionEvaluationResponse,
)
from app.providers.vision.openai_compatible import call_openai_compatible


def _join_url(base: str, suffix: str) -> str:
    return base.rstrip("/") + suffix


class LocalVisionProvider(VisionProvider):
    provider_adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float,
        max_images: int,
        verify_tls: bool,
        max_retries: int = 0,
        log_raw_text: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._max_images = max_images
        self._max_retries = max_retries
        self._log_raw_text = log_raw_text
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            verify=verify_tls,
        )
        self._chat_url = self._base_url + "/chat/completions"
        self._models_url = self._base_url + "/models"

    @property
    def info(self) -> VisionProviderInfo:
        return VisionProviderInfo(
            provider_name="local",
            model_id=self._model,
            provider_adapter_version=self.provider_adapter_version,
        )

    @property
    def capabilities(self) -> VisionProviderCapabilities:
        return VisionProviderCapabilities(
            max_images_per_request=self._max_images,
            max_image_bytes=20 * 1024 * 1024,
            max_total_request_bytes=20 * 1024 * 1024,
            supports_structured_output=True,
            supports_inline_images=True,
        )

    async def evaluate(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse:
        return await run_with_retries(lambda: self._evaluate_once(request), self._max_retries)

    async def _evaluate_once(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse:
        return await call_openai_compatible(
            self._client,
            url=self._chat_url,
            api_key=self._api_key,
            model=self._model,
            provider_name="local",
            frame_strategy=request.provider_options.get("frame_strategy"),
            request=request,
            on_raw_text=self._log_raw_text_callable() if self._log_raw_text else None,
        )

    def _log_raw_text_callable(self) -> Callable[[str], None]:
        from app.core.logging import get_logger, redact_raw_text

        logger = get_logger("livephoto.vlm.local")

        def _log(text: str) -> None:
            logger.info(
                "vlm_local_raw_response",
                provider="local",
                model=self._model,
                raw_text=redact_raw_text(text),
            )

        return _log

    async def health(self) -> ProviderHealth:
        """Lightweight capability check via ``GET <base>/models`` where supported.

        Never called during startup and never raises (health failure must not crash LivePhoto).
        The base URL is intentionally NOT exposed beyond this adapter.
        """
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
            response = await self._client.get(self._models_url, headers=headers)
            if response.status_code == 200:
                return ProviderHealth(status="ok", detail="local model endpoint reachable")
            if response.status_code in (401, 403):
                return ProviderHealth(status="degraded", detail="local model auth check failed")
            return ProviderHealth(
                status="degraded", detail="local model endpoint returned an error"
            )
        except Exception:
            return ProviderHealth(status="error", detail="local model endpoint unreachable")
