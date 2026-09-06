"""VisionProvider contract (M0 ADR-005, M4 §21-23).

Providers are replaceable and expose explicit info + capabilities. Business workflows depend only on
this interface; the future self-hosted provider (LocalVisionProvider) uses the same contract (M4
§162).
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from app.providers.vision.models import VisionEvaluationRequest, VisionEvaluationResponse


class VisionProviderInfo(BaseModel):
    provider_name: str
    model_id: str
    provider_adapter_version: str


class VisionProviderCapabilities(BaseModel):
    max_images_per_request: int
    max_image_bytes: int
    max_total_request_bytes: int
    supports_structured_output: bool = True
    supports_inline_images: bool = True


class ProviderHealth(BaseModel):
    status: Literal["ok", "degraded", "error"]
    detail: str | None = None


@runtime_checkable
class VisionProvider(Protocol):
    """A provider adapter that evaluates image(s) and returns a normalized response."""

    @property
    def info(self) -> VisionProviderInfo: ...

    @property
    def capabilities(self) -> VisionProviderCapabilities: ...

    async def evaluate(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse: ...

    async def health(self) -> ProviderHealth: ...
