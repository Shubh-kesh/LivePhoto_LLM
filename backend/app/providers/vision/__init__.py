"""Vision-language model provider package (M0 ADR-005, M1 §29, M4 §21-27).

External VLMs are POC-only and receive only approved, non-sensitive test images
(``docs/VLM_EXTERNAL_PROVIDER_POLICY.md``). Production targets a self-hosted provider behind the
same ``VisionProvider`` contract (M4 §162).
"""

from app.providers.vision.contracts import (
    ProviderHealth,
    VisionProvider,
    VisionProviderCapabilities,
    VisionProviderInfo,
)
from app.providers.vision.errors import VlmError, VlmErrorCode, VlmNotConfiguredError
from app.providers.vision.models import (
    VLM_SCHEMA_VERSION,
    AttackMedium,
    EvidenceCode,
    ImageInput,
    SecondaryPersonState,
    SubjectCount,
    TokenUsage,
    VisionEvaluationRequest,
    VisionEvaluationResponse,
    VlmAssessment,
    VlmClassification,
)
from app.providers.vision.prompts import PROMPT_ID, PROMPT_VERSION, SYSTEM_PROMPT
from app.providers.vision.registry import available_providers, get_vision_provider

__all__ = [
    "PROMPT_ID",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "VLM_SCHEMA_VERSION",
    "AttackMedium",
    "EvidenceCode",
    "ImageInput",
    "ProviderHealth",
    "SecondaryPersonState",
    "SubjectCount",
    "TokenUsage",
    "VisionEvaluationRequest",
    "VisionEvaluationResponse",
    "VisionProvider",
    "VisionProviderCapabilities",
    "VisionProviderInfo",
    "VlmAssessment",
    "VlmClassification",
    "VlmError",
    "VlmErrorCode",
    "VlmNotConfiguredError",
    "available_providers",
    "get_vision_provider",
]
