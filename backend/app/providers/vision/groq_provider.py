"""Groq vision provider (M4 §9, §27-29).

OpenAI-compatible chat completions with inline data-URL images.
"""

from __future__ import annotations

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

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqVisionProvider(VisionProvider):
    provider_adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_retries = max_retries
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    @property
    def info(self) -> VisionProviderInfo:
        return VisionProviderInfo(
            provider_name="groq",
            model_id=self._model,
            provider_adapter_version=self.provider_adapter_version,
        )

    @property
    def capabilities(self) -> VisionProviderCapabilities:
        return VisionProviderCapabilities(
            max_images_per_request=8,
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
            url=GROQ_URL,
            api_key=self._api_key,
            model=self._model,
            provider_name="groq",
            frame_strategy=request.provider_options.get("frame_strategy"),
            request=request,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            status="ok" if self._api_key else "error",
            detail="configured" if self._api_key else "missing key",
        )
