"""VLM provider tests (M4 §77): mocked network for Gemini/OpenRouter/Groq, deterministic mock."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.providers.vision import (
    AttackMedium,
    VisionEvaluationRequest,
    VlmClassification,
    VlmError,
    VlmErrorCode,
)
from app.providers.vision.gemini_provider import GeminiVisionProvider
from app.providers.vision.groq_provider import GroqVisionProvider
from app.providers.vision.mock_provider import MockVisionProvider
from app.providers.vision.models import ImageInput
from app.providers.vision.openrouter_provider import OpenRouterVisionProvider


def _request(strategy: str = "single-quality-v1") -> VisionEvaluationRequest:
    return VisionEvaluationRequest(
        images=[ImageInput(bytes=b"\xff\xd8\xfffakejpeg", mime_type="image/jpeg", sequence=0)],
        prompt_id="passive-liveness",
        prompt_version="vlm-passive-v3",
        temperature=0.0,
        provider_options={"frame_strategy": strategy},
    )


def _valid_openai_body(text: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


VALID_ASSESSMENT_JSON = json.dumps(
    {
        "classification": "SCREEN_REPLAY",
        "attack_medium": "MOBILE_SCREEN",
        "self_reported_confidence": 0.86,
        "evidence_codes": ["DEVICE_BORDER_VISIBLE"],
        "subject_count": "ONE",
        "secondary_person_state": "NONE",
    }
)


def _mock_openai_transport(responses: list[httpx.Response]) -> httpx.MockTransport:
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return next(iterator)

    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_openrouter_success() -> None:
    client = httpx.AsyncClient(
        transport=_mock_openai_transport(
            [httpx.Response(200, json=_valid_openai_body(VALID_ASSESSMENT_JSON))]
        )
    )
    provider = OpenRouterVisionProvider(
        api_key="k", model="openai/gpt-4o", timeout_seconds=5, max_retries=0, client=client
    )
    response = await provider.evaluate(_request())
    assert response.provider == "openrouter"
    assert response.model == "openai/gpt-4o"
    assert response.assessment.classification is VlmClassification.SCREEN_REPLAY
    assert response.usage is not None
    assert response.usage.total_tokens == 15
    assert response.provider_request_id == "chatcmpl-1"
    await client.aclose()


@pytest.mark.anyio
async def test_groq_success() -> None:
    client = httpx.AsyncClient(
        transport=_mock_openai_transport(
            [httpx.Response(200, json=_valid_openai_body(VALID_ASSESSMENT_JSON))]
        )
    )
    provider = GroqVisionProvider(
        api_key="k",
        model="llama-3.2-11b-vision-preview",
        timeout_seconds=5,
        max_retries=0,
        client=client,
    )
    response = await provider.evaluate(_request())
    assert response.provider == "groq"
    assert response.assessment.classification is VlmClassification.SCREEN_REPLAY
    await client.aclose()


@pytest.mark.anyio
async def test_openai_provider_rate_limited() -> None:
    client = httpx.AsyncClient(
        transport=_mock_openai_transport([httpx.Response(429, json={"error": "rate"})])
    )
    provider = OpenRouterVisionProvider(
        api_key="k", model="m", timeout_seconds=5, max_retries=0, client=client
    )
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.PROVIDER_RATE_LIMITED
    await client.aclose()


@pytest.mark.anyio
async def test_openai_provider_auth_error() -> None:
    client = httpx.AsyncClient(
        transport=_mock_openai_transport([httpx.Response(401, json={"error": "auth"})])
    )
    provider = GroqVisionProvider(
        api_key="k", model="m", timeout_seconds=5, max_retries=0, client=client
    )
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.PROVIDER_AUTH_ERROR
    await client.aclose()


@pytest.mark.anyio
async def test_openai_provider_5xx_unavailable() -> None:
    client = httpx.AsyncClient(
        transport=_mock_openai_transport([httpx.Response(503, json={"error": "down"})])
    )
    provider = OpenRouterVisionProvider(
        api_key="k", model="m", timeout_seconds=5, max_retries=0, client=client
    )
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.PROVIDER_UNAVAILABLE
    await client.aclose()


@pytest.mark.anyio
async def test_openai_provider_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterVisionProvider(
        api_key="k", model="m", timeout_seconds=5, max_retries=0, client=client
    )
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.PROVIDER_TIMEOUT
    await client.aclose()


@pytest.mark.anyio
async def test_openai_provider_invalid_json_is_schema_error() -> None:
    client = httpx.AsyncClient(
        transport=_mock_openai_transport([httpx.Response(200, json=_valid_openai_body("not json"))])
    )
    provider = GroqVisionProvider(
        api_key="k", model="m", timeout_seconds=5, max_retries=0, client=client
    )
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.SCHEMA_VALIDATION_ERROR
    await client.aclose()


@pytest.mark.anyio
async def test_openai_provider_schema_violation() -> None:
    bad = json.dumps(
        {
            "classification": "MAYBE",
            "attack_medium": "NONE",
            "self_reported_confidence": 0.5,
            "evidence_codes": [],
        }
    )
    client = httpx.AsyncClient(
        transport=_mock_openai_transport([httpx.Response(200, json=_valid_openai_body(bad))])
    )
    provider = GroqVisionProvider(
        api_key="k", model="m", timeout_seconds=5, max_retries=0, client=client
    )
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.SCHEMA_VALIDATION_ERROR
    await client.aclose()


@pytest.mark.anyio
async def test_gemini_success() -> None:
    provider = GeminiVisionProvider(
        api_key="dummy", model="gemini-2.0-flash", timeout_seconds=5, max_retries=0
    )
    fake_response = SimpleNamespace(text=VALID_ASSESSMENT_JSON, usage_metadata=None)
    fake_models = SimpleNamespace(generate_content=AsyncMock(return_value=fake_response))
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=fake_models))  # type: ignore[attr-defined]
    response = await provider.evaluate(_request())
    assert response.provider == "gemini"
    assert response.assessment.classification is VlmClassification.SCREEN_REPLAY


@pytest.mark.anyio
async def test_gemini_rate_limited() -> None:
    class FakeAPIError(Exception):
        def __init__(self, code: int) -> None:
            self.code = code
            super().__init__("boom")

    provider = GeminiVisionProvider(
        api_key="dummy", model="gemini-2.0-flash", timeout_seconds=5, max_retries=0
    )
    fake_models = SimpleNamespace(generate_content=AsyncMock(side_effect=FakeAPIError(429)))
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=fake_models))  # type: ignore[attr-defined]
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.PROVIDER_RATE_LIMITED


@pytest.mark.anyio
async def test_gemini_invalid_output_is_schema_error() -> None:
    provider = GeminiVisionProvider(
        api_key="dummy", model="gemini-2.0-flash", timeout_seconds=5, max_retries=0
    )
    fake_models = SimpleNamespace(
        generate_content=AsyncMock(return_value=SimpleNamespace(text="nope", usage_metadata=None))
    )
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=fake_models))  # type: ignore[attr-defined]
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request())
    assert exc.value.code is VlmErrorCode.SCHEMA_VALIDATION_ERROR


@pytest.mark.anyio
async def test_mock_provider_behaviors() -> None:
    provider = MockVisionProvider(timeout_seconds=1)
    live_request = _request()
    live_request.provider_options["mock_behavior"] = "live"
    live = await provider.evaluate(live_request)
    assert live.assessment.classification is VlmClassification.LIVE
    assert live.assessment.attack_medium is AttackMedium.NONE

    screen = await provider.evaluate(_request())
    assert screen.assessment.classification is VlmClassification.SCREEN_REPLAY
    assert screen.provider == "mock"
    assert screen.provider_request_id == "mock-request-id"


@pytest.mark.anyio
async def test_mock_provider_timeout_behavior() -> None:
    provider = MockVisionProvider(timeout_seconds=0.01)
    request = _request()
    request.provider_options["mock_behavior"] = "timeout"
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(request)
    assert exc.value.code is VlmErrorCode.PROVIDER_TIMEOUT


@pytest.mark.anyio
async def test_mock_provider_auth_behavior() -> None:
    provider = MockVisionProvider()
    request = _request()
    request.provider_options["mock_behavior"] = "auth"
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(request)
    assert exc.value.code is VlmErrorCode.PROVIDER_AUTH_ERROR
