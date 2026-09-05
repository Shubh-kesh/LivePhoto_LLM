"""Vision-language model provider seam (M0 ADR-005, M1 §29).

M1 defines the abstraction only. **No external AI is called and no AI keys exist in M1
configuration.** Actual providers (Gemini / Groq / OpenRouter / Local / Mock) start in M4.

External VLM usage is restricted to approved, non-sensitive POC/demo images
(``docs/DATA_GOVERNANCE.md``); production targets a self-hosted model inside bank-controlled
infrastructure.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class VisionPrompt(BaseModel):
    """Versioned prompt definition — prompts are versioned like model artifacts (M0 §35)."""

    provider: str
    model: str
    prompt_id: str
    prompt_version: str
    schema_version: str = "1"
    temperature: float | None = None
    settings: dict[str, object] = Field(default_factory=dict)


class VisionProviderResult(BaseModel):
    provider: str
    model: str
    result: Literal["LIVE", "SPOOF", "QUALITY_FAILURE", "UNCERTAIN"]
    raw_output: str | None = None
    latency_ms: int | None = None
    prompt_version: str | None = None


@runtime_checkable
class VisionProvider(Protocol):
    """A provider that evaluates image(s) against a versioned prompt.

    Implementations connect to external/local models; the interface lets the application switch
    ``external -> local/self-hosted`` without rewriting business workflows.
    """

    provider_name: str

    def evaluate(self, images: Sequence[object], prompt: VisionPrompt) -> VisionProviderResult: ...


__all__ = ["VisionPrompt", "VisionProvider", "VisionProviderResult"]
