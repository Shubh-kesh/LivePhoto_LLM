"""Vision provider seam tests (M1 §29, evolved to the M4 contract)."""

from __future__ import annotations

from app.providers.vision import (
    AttackMedium,
    ProviderHealth,
    VisionEvaluationRequest,
    VisionEvaluationResponse,
    VisionProvider,
    VisionProviderCapabilities,
    VisionProviderInfo,
    VlmAssessment,
    VlmClassification,
)


class _FakeProvider:
    @property
    def info(self) -> VisionProviderInfo:
        return VisionProviderInfo(
            provider_name="mock",
            model_id="mock-vision-v1",
            provider_adapter_version="1.0.0",
        )

    @property
    def capabilities(self) -> VisionProviderCapabilities:
        return VisionProviderCapabilities(
            max_images_per_request=3,
            max_image_bytes=5 * 1024 * 1024,
            max_total_request_bytes=15 * 1024 * 1024,
        )

    async def evaluate(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse:
        return VisionEvaluationResponse(
            assessment=VlmAssessment(
                classification=VlmClassification.LIVE,
                attack_medium=AttackMedium.NONE,
                self_reported_confidence=0.95,
            ),
            provider="mock",
            model=self.info.model_id,
            provider_adapter_version="1.0.0",
            image_count=len(request.images),
            provider_latency_ms=1,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status="ok")


def test_fake_provider_conforms_to_protocol() -> None:
    assert isinstance(_FakeProvider(), VisionProvider)


def test_provider_exposes_info_and_capabilities() -> None:
    provider = _FakeProvider()
    assert provider.info.provider_name == "mock"
    assert provider.info.model_id == "mock-vision-v1"
    assert provider.capabilities.max_images_per_request == 3


def test_request_carries_prompt_versioning() -> None:
    request = VisionEvaluationRequest(
        images=[],
        prompt_id="passive-liveness",
        prompt_version="vlm-passive-v1",
        temperature=0.0,
    )
    assert request.prompt_version == "vlm-passive-v1"
    assert request.temperature == 0.0


def test_assessment_keeps_taxonomy_distinct() -> None:
    assessment = VlmAssessment(
        classification=VlmClassification.SCREEN_REPLAY,
        attack_medium=AttackMedium.MOBILE_SCREEN,
        self_reported_confidence=0.86,
    )
    data = assessment.model_dump()
    assert data["classification"] == "SCREEN_REPLAY"
    assert data["attack_medium"] == "MOBILE_SCREEN"
    assert data["self_reported_confidence"] == 0.86
    assert data["schema_version"] == "vlm-result-v1"


def test_assessment_rejects_unknown_classification() -> None:
    from pydantic import ValidationError

    try:
        VlmAssessment(
            classification="MAYBE",  # type: ignore[arg-type]
            attack_medium=AttackMedium.NONE,
            self_reported_confidence=0.5,
        )
    except ValidationError:
        return
    raise AssertionError("unknown classification should have been rejected")
