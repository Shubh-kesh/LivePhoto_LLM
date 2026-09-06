"""Normalized VLM result models (M4 §33-36, §56, §129).

Provider-independent taxonomy. `self_reported_confidence` is exactly what it says: the provider's
own claim, NOT a calibrated probability and never a liveness_score/spoof_probability (M4 §54-55).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

VLM_SCHEMA_VERSION = "vlm-result-v1"


class VlmClassification(StrEnum):
    LIVE = "LIVE"
    SCREEN_REPLAY = "SCREEN_REPLAY"
    PRINT_ATTACK = "PRINT_ATTACK"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    UNCERTAIN = "UNCERTAIN"


class AttackMedium(StrEnum):
    MOBILE_SCREEN = "MOBILE_SCREEN"
    TABLET_SCREEN = "TABLET_SCREEN"
    LAPTOP_SCREEN = "LAPTOP_SCREEN"
    MONITOR = "MONITOR"
    PRINT_PHOTO = "PRINT_PHOTO"
    NEWSPAPER = "NEWSPAPER"
    MAGAZINE = "MAGAZINE"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"


class EvidenceCode(StrEnum):
    DEVICE_BORDER_VISIBLE = "DEVICE_BORDER_VISIBLE"
    SCREEN_EDGE_VISIBLE = "SCREEN_EDGE_VISIBLE"
    DISPLAY_REFLECTION = "DISPLAY_REFLECTION"
    MOIRE_PATTERN = "MOIRE_PATTERN"
    PIXEL_GRID_PATTERN = "PIXEL_GRID_PATTERN"
    DISPLAY_GLARE = "DISPLAY_GLARE"
    PAPER_EDGE_VISIBLE = "PAPER_EDGE_VISIBLE"
    PAPER_TEXTURE = "PAPER_TEXTURE"
    PRINT_HALFTONE_PATTERN = "PRINT_HALFTONE_PATTERN"
    FLAT_PRINT_APPEARANCE = "FLAT_PRINT_APPEARANCE"
    ENVIRONMENT_CONSISTENT_WITH_LIVE = "ENVIRONMENT_CONSISTENT_WITH_LIVE"
    NATURAL_SCENE_DEPTH_CUES = "NATURAL_SCENE_DEPTH_CUES"
    INSUFFICIENT_VISUAL_EVIDENCE = "INSUFFICIENT_VISUAL_EVIDENCE"
    NONE = "NONE"


class VlmAssessment(BaseModel):
    """Strict structured provider output (M4 §36, §52, §129). Extra fields are forbidden.

    ``classification`` and ``attack_medium`` are strict enums; ``evidence_codes`` are retained as
    bounded strings because real providers emit codes beyond the controlled ``EvidenceCode``
    vocabulary. Known codes map to the documented enum; unknown codes are kept as observations and
    never treated as ground truth (M4 §38). A wrong evidence code does not invalidate an otherwise
    valid classification.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = VLM_SCHEMA_VERSION
    classification: VlmClassification
    attack_medium: AttackMedium = AttackMedium.NONE
    self_reported_confidence: float = Field(ge=0.0, le=1.0)
    evidence_codes: list[str] = Field(default_factory=list, max_length=20)


class TokenUsage(BaseModel):
    """Provider-reported token usage; never invented when absent (M4 §57)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ImageInput(BaseModel):
    bytes: bytes
    mime_type: str
    sequence: int | None = None


class VisionEvaluationRequest(BaseModel):
    """Normalized request a provider adapter receives (M4 §21, §162)."""

    images: list[ImageInput]
    prompt_id: str
    prompt_version: str
    schema_version: str = VLM_SCHEMA_VERSION
    temperature: float = 0.0
    provider_options: dict[str, str] = Field(default_factory=dict)


class VisionEvaluationResponse(BaseModel):
    assessment: VlmAssessment
    provider: str
    model: str
    provider_adapter_version: str
    frame_strategy: str | None = None
    image_count: int
    provider_latency_ms: int
    usage: TokenUsage | None = None
    provider_request_id: str | None = None
    error: VlmErrorCode | None = None


from app.providers.vision.errors import VlmErrorCode  # noqa: E402
