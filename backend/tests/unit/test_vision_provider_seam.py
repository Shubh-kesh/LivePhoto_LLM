"""Vision provider seam tests (M1 §29)."""

from __future__ import annotations

from collections.abc import Sequence

from app.providers.vision import (
    VisionPrompt,
    VisionProvider,
    VisionProviderResult,
)


class _FakeProvider:
    provider_name = "mock"

    def evaluate(self, images: Sequence[object], prompt: VisionPrompt) -> VisionProviderResult:
        return VisionProviderResult(
            provider=self.provider_name,
            model=prompt.model,
            result="LIVE",
            prompt_version=prompt.prompt_version,
        )


def test_fake_provider_conforms_to_protocol() -> None:
    assert isinstance(_FakeProvider(), VisionProvider)


def test_vision_prompt_carries_versioning_fields() -> None:
    prompt = VisionPrompt(
        provider="openrouter",
        model="gpt-vision",
        prompt_id="lp-prompts/device/v3",
        prompt_version="3",
        temperature=0.0,
    )
    assert prompt.provider == "openrouter"
    assert prompt.prompt_version == "3"
    assert prompt.schema_version == "1"


def test_vision_provider_result_shape() -> None:
    result = VisionProviderResult(
        provider="gemini", model="gemini-x", result="SPOOF", latency_ms=1500
    )
    data = result.model_dump()
    assert data["result"] == "SPOOF"
    assert data["latency_ms"] == 1500
    assert data["raw_output"] is None


def test_provider_result_enforces_known_outcomes() -> None:
    try:
        from pydantic import ValidationError

        VisionProviderResult(provider="x", model="y", result="MAYBE")
    except ValidationError:
        return
    raise AssertionError("invalid outcome should have been rejected")
