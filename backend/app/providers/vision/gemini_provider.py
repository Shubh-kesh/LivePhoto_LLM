"""Gemini vision provider (M4 §9, §27-29).

Official google-genai SDK; structured output via response_schema where supported; inline images
only (no Files API by default, M4 §14).
"""

from __future__ import annotations

import base64
import time
from typing import Any

from app.providers.vision.base import parse_assessment, run_with_retries, timing_ms
from app.providers.vision.contracts import (
    ProviderHealth,
    VisionProvider,
    VisionProviderCapabilities,
    VisionProviderInfo,
)
from app.providers.vision.errors import (
    RETRYABLE_STATUS_CODES,
    VlmError,
    VlmErrorCode,
)
from app.providers.vision.models import (
    TokenUsage,
    VisionEvaluationRequest,
    VisionEvaluationResponse,
)
from app.providers.vision.prompts import USER_PROMPT

ASSESSMENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": ["LIVE", "SCREEN_REPLAY", "PRINT_ATTACK", "QUALITY_FAILURE", "UNCERTAIN"],
        },
        "attack_medium": {
            "type": "string",
            "enum": [
                "MOBILE_SCREEN",
                "TABLET_SCREEN",
                "LAPTOP_SCREEN",
                "MONITOR",
                "PRINT_PHOTO",
                "NEWSPAPER",
                "MAGAZINE",
                "UNKNOWN",
                "NONE",
            ],
        },
        "self_reported_confidence": {"type": "number"},
        "evidence_codes": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "DEVICE_BORDER_VISIBLE",
                    "SCREEN_EDGE_VISIBLE",
                    "DISPLAY_REFLECTION",
                    "MOIRE_PATTERN",
                    "PIXEL_GRID_PATTERN",
                    "DISPLAY_GLARE",
                    "PAPER_EDGE_VISIBLE",
                    "PAPER_TEXTURE",
                    "PRINT_HALFTONE_PATTERN",
                    "FLAT_PRINT_APPEARANCE",
                    "ENVIRONMENT_CONSISTENT_WITH_LIVE",
                    "NATURAL_SCENE_DEPTH_CUES",
                    "INSUFFICIENT_VISUAL_EVIDENCE",
                    "NONE",
                ],
            },
        },
    },
    "required": [
        "classification",
        "attack_medium",
        "self_reported_confidence",
        "evidence_codes",
    ],
}


def _map_gemini_error(exc: Exception) -> VlmError:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status in (401, 403):
            return VlmError(VlmErrorCode.PROVIDER_AUTH_ERROR, "gemini authentication failed")
        if status == 429:
            return VlmError(VlmErrorCode.PROVIDER_RATE_LIMITED, "gemini rate limited")
        if status in RETRYABLE_STATUS_CODES:
            return VlmError(VlmErrorCode.PROVIDER_UNAVAILABLE, "gemini unavailable")
        if 400 <= status < 500:
            return VlmError(VlmErrorCode.PROVIDER_BAD_REQUEST, "gemini rejected the request")
    return VlmError(VlmErrorCode.UNKNOWN_PROVIDER_ERROR, str(exc))


class GeminiVisionProvider(VisionProvider):
    provider_adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        from google import genai
        from google.genai import types

        self._model = model
        self._max_retries = max_retries
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_seconds * 1000),
        )
        self._genai_types = types

    @property
    def info(self) -> VisionProviderInfo:
        return VisionProviderInfo(
            provider_name="gemini",
            model_id=self._model,
            provider_adapter_version=self.provider_adapter_version,
        )

    @property
    def capabilities(self) -> VisionProviderCapabilities:
        return VisionProviderCapabilities(
            max_images_per_request=16,
            max_image_bytes=20 * 1024 * 1024,
            max_total_request_bytes=20 * 1024 * 1024,
            supports_structured_output=True,
            supports_inline_images=True,
        )

    async def evaluate(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse:
        return await run_with_retries(lambda: self._evaluate_once(request), self._max_retries)

    async def _evaluate_once(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse:
        types_ = self._genai_types
        parts: list[Any] = []
        for image in request.images:
            parts.append(
                types_.Part(
                    inline_data=types_.Blob(
                        mime_type=image.mime_type,
                        data=base64.b64encode(image.bytes).decode("ascii"),
                    )
                )
            )
        parts.append(types_.Part(text=USER_PROMPT))

        config = types_.GenerateContentConfig(
            temperature=request.temperature,
            response_mime_type="application/json",
            response_schema=ASSESSMENT_JSON_SCHEMA,
        )

        started = time.perf_counter()
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=list(parts),
                config=config,
            )
        except Exception as exc:
            raise _map_gemini_error(exc) from exc

        latency_ms = timing_ms(started)
        text = (response.text or "").strip()
        if not text:
            raise VlmError(VlmErrorCode.PROVIDER_RESPONSE_ERROR, "empty gemini response")
        assessment = parse_assessment(text)

        usage: TokenUsage | None = None
        metadata = getattr(response, "usage_metadata", None)
        if metadata is not None:
            usage = TokenUsage(
                input_tokens=getattr(metadata, "prompt_token_count", None),
                output_tokens=getattr(metadata, "candidates_token_count", None),
                total_tokens=getattr(metadata, "total_token_count", None),
            )

        return VisionEvaluationResponse(
            assessment=assessment,
            provider="gemini",
            model=self._model,
            provider_adapter_version=self.provider_adapter_version,
            frame_strategy=request.provider_options.get("frame_strategy"),
            image_count=len(request.images),
            provider_latency_ms=latency_ms,
            usage=usage,
            provider_request_id=None,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status="ok", detail="gemini configured")
