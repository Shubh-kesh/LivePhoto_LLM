"""Optional LIVE external-VLM smoke tests (M4 §79-80, §149-150).

Run only when VLM_LIVE_TESTS_ENABLED=true AND the selected provider credential is configured.
Never runs in ordinary CI. Uses an approved non-sensitive synthetic image (generated at runtime;
no face, no bank data).

A provider returning valid JSON here proves connectivity + structured output — it does NOT prove
liveness accuracy (M4 §150).
"""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from app.core.config import Settings
from app.experiments.vlm.service import ExperimentEvaluateRequest, VlmEvaluationService
from app.providers.vision.models import ImageInput

pytestmark = [pytest.mark.live_vlm]


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (90, 90, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _provider_keyed() -> bool:
    provider = os.getenv("VLM_PROVIDER", "")
    if provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY")) and bool(os.getenv("GEMINI_MODEL"))
    if provider == "groq":
        return bool(os.getenv("GROQ_API_KEY")) and bool(os.getenv("GROQ_MODEL"))
    if provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY")) and bool(os.getenv("OPENROUTER_MODEL"))
    return False


@pytest.mark.skipif(
    os.getenv("VLM_LIVE_TESTS_ENABLED") != "true", reason="VLM_LIVE_TESTS_ENABLED not set"
)
@pytest.mark.anyio
async def test_live_provider_structured_evaluation() -> None:
    provider = os.getenv("VLM_PROVIDER", "")
    if not _provider_keyed():
        pytest.skip(f"provider '{provider}' not fully configured")

    settings = Settings()
    service = VlmEvaluationService(settings)
    request = ExperimentEvaluateRequest(
        strategy="single-quality-v1",
        capture_config_version="capture-v1",
        quality_config_version="quality-v1",
        frame_selection_version="single-quality-v1",
        provider=provider,
        frames=[ImageInput(bytes=_jpeg_bytes(), mime_type="image/jpeg", sequence=0)],
    )
    result = await service.evaluate(request)
    assert result.error is None, f"provider error: {result.error}"
    assert result.classification in {
        "LIVE",
        "SCREEN_REPLAY",
        "PRINT_ATTACK",
        "QUALITY_FAILURE",
        "UNCERTAIN",
    }
    print(
        f"LIVE_PROVIDER_RESULT provider={result.provider} model={result.model} "
        f"image_count={result.image_count} classification={result.classification} "
        f"latency_ms={result.latency_ms}"
    )
