"""VlmEvaluationService tests (M4 §75, §145)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.experiments.vlm.service import ExperimentEvaluateRequest, VlmEvaluationService
from app.providers.vision import VlmError, VlmErrorCode
from app.providers.vision.mock_provider import MockVisionProvider
from app.providers.vision.models import ImageInput


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "app_env": "test",
        "vlm_experiment_enabled": True,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


def _request(
    strategy: str = "single-quality-v1", frame_count: int = 1
) -> ExperimentEvaluateRequest:
    return ExperimentEvaluateRequest(
        strategy=strategy,  # type: ignore[arg-type]
        provider="mock",
        frames=[
            ImageInput(bytes=b"\xff\xd8\xfffake", mime_type="image/jpeg", sequence=i)
            for i in range(frame_count)
        ],
    )


def _service(settings: Settings) -> VlmEvaluationService:
    return VlmEvaluationService(settings, provider_factory=lambda s, name: MockVisionProvider())


@pytest.mark.anyio
async def test_disabled_experiment_raises_vlm_disabled() -> None:
    service = _service(_settings(vlm_experiment_enabled=False))
    with pytest.raises(VlmError) as exc:
        await service.evaluate(_request())
    assert exc.value.code is VlmErrorCode.VLM_DISABLED


@pytest.mark.anyio
async def test_production_prohibition_even_when_enabled() -> None:
    service = _service(_settings(app_env="uat", vlm_experiment_enabled=True))
    with pytest.raises(VlmError) as exc:
        await service.evaluate(_request())
    assert exc.value.code is VlmErrorCode.VLM_DISABLED


@pytest.mark.anyio
async def test_strategy_frame_count_validation() -> None:
    service = _service(_settings())
    with pytest.raises(VlmError) as exc:
        await service.evaluate(_request("single-quality-v1", frame_count=2))
    assert exc.value.code is VlmErrorCode.PROVIDER_BAD_REQUEST


@pytest.mark.anyio
async def test_too_many_images_capability_check() -> None:
    settings = _settings(vlm_max_frames=1)
    service = _service(settings)
    with pytest.raises(VlmError) as exc:
        await service.evaluate(_request("temporal-triad-v1", frame_count=3))
    assert exc.value.code is VlmErrorCode.TOO_MANY_IMAGES


@pytest.mark.anyio
async def test_oversized_image_rejected() -> None:
    settings = _settings(vlm_max_single_image_bytes=4)
    service = _service(settings)
    with pytest.raises(VlmError) as exc:
        await service.evaluate(_request())
    assert exc.value.code is VlmErrorCode.REQUEST_TOO_LARGE


@pytest.mark.anyio
async def test_successful_mock_evaluation() -> None:
    service = _service(_settings())
    result = await service.evaluate(_request("single-quality-v1", 1))
    assert result.classification == "SCREEN_REPLAY"
    assert result.provider == "mock"
    assert result.error is None
    assert result.latency_ms is not None
    assert result.prompt_version == "vlm-passive-v3"
    assert result.schema_version == "vlm-result-v3"
    assert result.subject_count == "ONE"
    assert result.secondary_person_state == "NONE"
    assert result.frame_strategy == "single-quality-v1"
    assert result.image_count == 1


@pytest.mark.anyio
async def test_mock_behavior_uncertain() -> None:
    request = _request()
    request.mock_behavior = "uncertain"
    service = _service(_settings())
    result = await service.evaluate(request)
    assert result.classification == "UNCERTAIN"


@pytest.mark.anyio
async def test_provider_error_never_becomes_live() -> None:
    request = _request()
    request.mock_behavior = "timeout"
    service = _service(_settings())
    result = await service.evaluate(request)
    assert result.error == "PROVIDER_TIMEOUT"
    assert result.classification is None
