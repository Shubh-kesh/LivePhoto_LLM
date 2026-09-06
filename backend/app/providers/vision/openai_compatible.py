"""OpenAI-compatible chat-completions transport for OpenRouter/Groq (M4 §29, §53).

Bounded inline images only (data URLs) — no provider file-storage APIs (M4 §14).
"""

from __future__ import annotations

import base64
import json

import httpx

from app.providers.vision.base import parse_assessment, timing_ms
from app.providers.vision.errors import (
    VlmError,
    VlmErrorCode,
    map_provider_http_error,
)
from app.providers.vision.models import (
    TokenUsage,
    VisionEvaluationRequest,
    VisionEvaluationResponse,
)
from app.providers.vision.prompts import SYSTEM_PROMPT, USER_PROMPT


def build_openai_messages(request: VisionEvaluationRequest) -> list[dict[str, object]]:
    content: list[dict[str, object]] = [{"type": "text", "text": USER_PROMPT}]
    for image in request.images:
        data = base64.b64encode(image.bytes).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.mime_type};base64,{data}"},
            }
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def parse_openai_response(body: dict[str, object]) -> tuple[str, TokenUsage | None]:
    """Return (choice_text, usage). Raises PROVIDER_RESPONSE_ERROR on malformed shape."""
    try:
        choice = body["choices"][0]  # type: ignore[index]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VlmError(VlmErrorCode.PROVIDER_RESPONSE_ERROR, "malformed provider response") from exc
    if not isinstance(text, str) or not text.strip():
        raise VlmError(VlmErrorCode.PROVIDER_RESPONSE_ERROR, "empty provider response content")

    usage: TokenUsage | None = None
    raw_usage = body.get("usage")
    if isinstance(raw_usage, dict):
        usage = TokenUsage(
            input_tokens=raw_usage.get("prompt_tokens"),
            output_tokens=raw_usage.get("completion_tokens"),
            total_tokens=raw_usage.get("total_tokens"),
        )
    return text, usage


async def call_openai_compatible(
    client: httpx.AsyncClient,
    *,
    url: str,
    api_key: str,
    model: str,
    provider_name: str,
    frame_strategy: str | None,
    request: VisionEvaluationRequest,
) -> VisionEvaluationResponse:
    payload = {
        "model": model,
        "messages": build_openai_messages(request),
        "temperature": request.temperature,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    started_at = time_perf_counter()
    try:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        raise map_provider_http_error(exc) from exc
    except Exception as exc:
        raise map_provider_http_error(exc) from exc

    text, usage = parse_openai_response(body)
    assessment = parse_assessment(text)
    latency_ms = timing_ms(started_at)
    request_id = str(body.get("id")) if body.get("id") else None

    return VisionEvaluationResponse(
        assessment=assessment,
        provider=provider_name,
        model=model,
        provider_adapter_version="1.0.0",
        frame_strategy=frame_strategy,
        image_count=len(request.images),
        provider_latency_ms=latency_ms,
        usage=usage,
        provider_request_id=request_id,
    )


def time_perf_counter() -> float:
    import time

    return time.perf_counter()


def _json_dumps_pretty(obj: object) -> str:
    return json.dumps(obj, sort_keys=True)
