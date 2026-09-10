"""LocalVisionProvider (OpenAI-compatible) tests (M5.6 §70). No real Gemma server required."""

from __future__ import annotations

import httpx
import pytest

from app.providers.vision.errors import VlmError, VlmErrorCode
from app.providers.vision.local_provider import LocalVisionProvider
from app.providers.vision.models import ImageInput, VisionEvaluationRequest

VALID_JSON = (
    '{"schema_version":"vlm-result-v3","classification":"SCREEN_REPLAY",'
    '"attack_medium":"MOBILE_SCREEN","self_reported_confidence":0.87,'
    '"evidence_codes":["DEVICE_BORDER_VISIBLE"],"subject_count":"ONE","secondary_person_state":"NONE"}'
)


def _request(count: int = 1) -> VisionEvaluationRequest:
    return VisionEvaluationRequest(
        images=[
            ImageInput(bytes=b"\xff\xd8\xff" + b"0" * 64, mime_type="image/jpeg")
            for _ in range(count)
        ],
        prompt_id="prompt-1",
        prompt_version="vlm-passive-v3",
        provider_options={"frame_strategy": "single-quality-v1"},
    )


def _provider(handler: httpx.MockTransport) -> LocalVisionProvider:
    return LocalVisionProvider(
        base_url="http://gemma:8000/v1",
        model="google/gemma-3-12b-it",
        api_key="secret-key",
        timeout_seconds=2.0,
        max_images=3,
        verify_tls=True,
        client=httpx.AsyncClient(transport=handler),
    )


def _json_body(content: str) -> dict[str, object]:
    return {
        "id": "req-local-1",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.mark.asyncio
async def test_single_image_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = request.read()
        assert b"image/jpeg;base64" in payload
        return httpx.Response(200, json=_json_body(VALID_JSON))

    provider = _provider(httpx.MockTransport(handler))
    result = await provider.evaluate(_request(1))
    assert result.provider == "local"
    assert result.assessment.classification.value == "SCREEN_REPLAY"
    assert result.assessment.attack_medium.value == "MOBILE_SCREEN"
    assert result.usage is not None and result.usage.input_tokens == 10
    assert result.provider_request_id == "req-local-1"


@pytest.mark.asyncio
async def test_three_images_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.read().count(b"data:image/jpeg;base64,") == 3
        return httpx.Response(200, json=_json_body(VALID_JSON))

    provider = _provider(httpx.MockTransport(handler))
    result = await provider.evaluate(_request(3))
    assert result.image_count == 3


@pytest.mark.asyncio
async def test_invalid_json_is_schema_error() -> None:
    provider = _provider(
        httpx.MockTransport(lambda r: httpx.Response(200, json=_json_body("not json")))
    )
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request(1))
    assert exc.value.code is VlmErrorCode.SCHEMA_VALIDATION_ERROR


@pytest.mark.asyncio
async def test_schema_violation_is_schema_error() -> None:
    bad = '{"classification":"NOT_A_REAL_CLASS","self_reported_confidence":2.0}'
    provider = _provider(httpx.MockTransport(lambda r: httpx.Response(200, json=_json_body(bad))))
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request(1))
    assert exc.value.code is VlmErrorCode.SCHEMA_VALIDATION_ERROR


@pytest.mark.asyncio
async def test_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request(1))
    assert exc.value.code is VlmErrorCode.PROVIDER_TIMEOUT


@pytest.mark.asyncio
async def test_connection_refused() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request(1))
    assert exc.value.code is VlmErrorCode.PROVIDER_UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors(status: int) -> None:
    provider = _provider(httpx.MockTransport(lambda r: httpx.Response(status, json={})))
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request(1))
    assert exc.value.code is VlmErrorCode.PROVIDER_AUTH_ERROR


@pytest.mark.asyncio
async def test_rate_limited() -> None:
    provider = _provider(httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request(1))
    assert exc.value.code is VlmErrorCode.PROVIDER_RATE_LIMITED


@pytest.mark.asyncio
async def test_server_error() -> None:
    provider = _provider(httpx.MockTransport(lambda r: httpx.Response(503, json={})))
    with pytest.raises(VlmError) as exc:
        await provider.evaluate(_request(1))
    assert exc.value.code is VlmErrorCode.PROVIDER_UNAVAILABLE


def test_image_count_limit_capability() -> None:
    provider = _provider(
        httpx.MockTransport(lambda r: httpx.Response(200, json=_json_body(VALID_JSON)))
    )
    assert provider.capabilities.max_images_per_request == 3
    assert provider.info.model_id == "google/gemma-3-12b-it"
    assert provider.info.provider_name == "local"


@pytest.mark.asyncio
async def test_health_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": []})

    provider = _provider(httpx.MockTransport(handler))
    health = await provider.health()
    assert health.status == "ok"


@pytest.mark.asyncio
async def test_health_error_does_not_raise() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    provider = _provider(httpx.MockTransport(handler))
    health = await provider.health()
    assert health.status == "error"


@pytest.mark.asyncio
async def test_health_auth_degraded() -> None:
    provider = _provider(httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    health = await provider.health()
    assert health.status == "degraded"
