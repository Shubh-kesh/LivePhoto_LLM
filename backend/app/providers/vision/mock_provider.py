"""Deterministic mock vision provider (M4 §27, §146).

Used for tests and the E2E mock backend. No network. Behavior is driven by
``request.provider_options["mock_behavior"]``:
default | live | print | uncertain | quality_failure | timeout | auth | schema | response_error.
Only ever active when provider == "mock" (never reachable from a real provider path).
"""

from __future__ import annotations

import asyncio

from app.providers.vision.base import timing_ms
from app.providers.vision.contracts import (
    ProviderHealth,
    VisionProvider,
    VisionProviderCapabilities,
    VisionProviderInfo,
)
from app.providers.vision.errors import VlmError, VlmErrorCode
from app.providers.vision.models import (
    AttackMedium,
    EvidenceCode,
    VisionEvaluationRequest,
    VisionEvaluationResponse,
    VlmAssessment,
    VlmClassification,
)

MOCK_MODEL_ID = "mock-vision-v1"


class MockVisionProvider(VisionProvider):
    provider_adapter_version = "1.0.0"

    def __init__(self, *, timeout_seconds: float = 1.0, max_retries: int = 0) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    @property
    def info(self) -> VisionProviderInfo:
        return VisionProviderInfo(
            provider_name="mock",
            model_id=MOCK_MODEL_ID,
            provider_adapter_version=self.provider_adapter_version,
        )

    @property
    def capabilities(self) -> VisionProviderCapabilities:
        return VisionProviderCapabilities(
            max_images_per_request=16,
            max_image_bytes=50 * 1024 * 1024,
            max_total_request_bytes=50 * 1024 * 1024,
            supports_structured_output=True,
            supports_inline_images=True,
        )

    async def evaluate(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse:
        behavior = request.provider_options.get("mock_behavior") or "default"
        started = timing_ms_start()
        if behavior == "timeout":
            await asyncio.sleep(self._timeout_seconds + 2.0)
            raise VlmError(VlmErrorCode.PROVIDER_TIMEOUT, "mock timeout")
        if behavior == "auth":
            raise VlmError(VlmErrorCode.PROVIDER_AUTH_ERROR, "mock auth failure")
        if behavior == "schema":
            # Invalid JSON shape -> SCHEMA_VALIDATION_ERROR (not silently fixed).
            return self._with_parse_failure()
        if behavior == "response_error":
            raise VlmError(VlmErrorCode.PROVIDER_RESPONSE_ERROR, "mock malformed response")

        assessment = _assessment_for(behavior)
        return VisionEvaluationResponse(
            assessment=assessment,
            provider="mock",
            model=MOCK_MODEL_ID,
            provider_adapter_version=self.provider_adapter_version,
            frame_strategy=request.provider_options.get("frame_strategy"),
            image_count=len(request.images),
            provider_latency_ms=timing_ms(started),
            usage=None,
            provider_request_id="mock-request-id",
        )

    def _with_parse_failure(self) -> VisionEvaluationResponse:
        raise VlmError(VlmErrorCode.SCHEMA_VALIDATION_ERROR, "mock invalid schema output")

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status="ok", detail="mock provider")


def _assessment_for(behavior: str) -> VlmAssessment:
    mapping: dict[str, tuple[VlmClassification, AttackMedium, float, list[EvidenceCode]]] = {
        "default": (
            VlmClassification.SCREEN_REPLAY,
            AttackMedium.UNKNOWN,
            0.87,
            [EvidenceCode.DEVICE_BORDER_VISIBLE, EvidenceCode.DISPLAY_REFLECTION],
        ),
        "screen_replay": (
            VlmClassification.SCREEN_REPLAY,
            AttackMedium.MOBILE_SCREEN,
            0.86,
            [EvidenceCode.DEVICE_BORDER_VISIBLE],
        ),
        "live": (
            VlmClassification.LIVE,
            AttackMedium.NONE,
            0.95,
            [EvidenceCode.ENVIRONMENT_CONSISTENT_WITH_LIVE],
        ),
        "print": (
            VlmClassification.PRINT_ATTACK,
            AttackMedium.PRINT_PHOTO,
            0.82,
            [EvidenceCode.PAPER_TEXTURE, EvidenceCode.PRINT_HALFTONE_PATTERN],
        ),
        "uncertain": (
            VlmClassification.UNCERTAIN,
            AttackMedium.UNKNOWN,
            0.4,
            [EvidenceCode.INSUFFICIENT_VISUAL_EVIDENCE],
        ),
        "quality_failure": (
            VlmClassification.QUALITY_FAILURE,
            AttackMedium.NONE,
            0.9,
            [EvidenceCode.INSUFFICIENT_VISUAL_EVIDENCE],
        ),
    }
    classification, medium, confidence, codes = mapping[behavior]
    return VlmAssessment(
        classification=classification,
        attack_medium=medium,
        self_reported_confidence=confidence,
        evidence_codes=codes,
    )


def timing_ms_start() -> float:
    import time

    return time.perf_counter()
