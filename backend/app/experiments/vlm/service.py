"""VlmEvaluationService (M4 §75).

Validates the experiment request, resolves the provider, checks capabilities, builds the prompt
request, executes the provider, validates the normalized result, records timings/metrics and
returns the experiment result. Routes stay thin.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.logging import get_logger
from app.observability.metrics import record_vlm_evaluation
from app.providers.vision import (
    PROMPT_ID,
    PROMPT_VERSION,
    VLM_SCHEMA_VERSION,
    VisionEvaluationRequest,
    VisionProvider,
    VlmError,
    VlmErrorCode,
    get_vision_provider,
)
from app.providers.vision.models import ImageInput, VisionEvaluationResponse

logger = get_logger("livephoto.vlm")


class ExperimentEvaluateRequest(BaseModel):
    strategy: Literal["single-quality-v1", "temporal-triad-v1"]
    capture_config_version: str = ""
    quality_config_version: str = ""
    frame_selection_version: str = ""
    provider: str
    mock_behavior: str = ""
    frames: list[ImageInput] = Field(default_factory=list)


class ExperimentResult(BaseModel):
    experiment: bool = True
    provider: str
    model: str
    prompt_version: str = PROMPT_VERSION
    schema_version: str = VLM_SCHEMA_VERSION
    frame_strategy: str
    image_count: int
    experiment_id: str = ""
    classification: str | None = None
    attack_medium: str | None = None
    self_reported_confidence: float | None = None
    evidence_codes: list[str] = Field(default_factory=list)
    #: Normalized visible-person category (ZERO|ONE|MULTIPLE|UNCERTAIN); None on provider error.
    subject_count: str | None = None
    #: Authoritative additional-person interference category; None on provider error.
    secondary_person_state: str | None = None
    latency_ms: int | None = None
    error: VlmErrorCode | None = None


class VlmEvaluationService:
    def __init__(
        self,
        settings: Settings,
        provider_factory: Callable[[Settings, str], VisionProvider] = get_vision_provider,
    ) -> None:
        self._settings = settings
        self._provider_factory = provider_factory

    def ensure_available(self) -> None:
        if not self._settings.vlm_experiment_available:
            raise VlmError(VlmErrorCode.VLM_DISABLED, "VLM experiment is not enabled")

    def _validate_strategy(self, strategy: str, count: int) -> None:
        from app.experiments.vlm.frame_selection import expected_frame_count

        expected = expected_frame_count(strategy)
        if count != expected:
            raise VlmError(
                VlmErrorCode.PROVIDER_BAD_REQUEST,
                f"strategy '{strategy}' requires {expected} frame(s), got {count}",
            )

    def _check_capabilities(
        self, provider: VisionProvider, request: ExperimentEvaluateRequest
    ) -> None:
        caps = provider.capabilities
        max_images = min(caps.max_images_per_request, self._settings.vlm_max_frames)
        if len(request.frames) > max_images:
            raise VlmError(
                VlmErrorCode.TOO_MANY_IMAGES, "too many images for this provider/request"
            )
        total = 0
        for image in request.frames:
            size = len(image.bytes)
            max_image = min(caps.max_image_bytes, self._settings.vlm_max_single_image_bytes)
            if size > max_image:
                raise VlmError(VlmErrorCode.REQUEST_TOO_LARGE, "single image exceeds the limit")
            total += size
        max_total = min(caps.max_total_request_bytes, self._settings.vlm_max_total_image_bytes)
        if total > max_total:
            raise VlmError(VlmErrorCode.REQUEST_TOO_LARGE, "total image bytes exceed the limit")

    def _log_request_started(
        self,
        request: ExperimentEvaluateRequest,
        provider: VisionProvider,
        experiment_id: str,
    ) -> None:
        if not self._settings.vlm_experiment_logging_enabled:
            return
        logger.info(
            "vlm_experiment_request_started",
            experiment_id=experiment_id,
            environment=self._settings.app_env,
            provider=request.provider,
            model=provider.info.model_id,
            provider_adapter_version=provider.info.provider_adapter_version,
            prompt_id=PROMPT_ID,
            prompt_version=PROMPT_VERSION,
            schema_version=VLM_SCHEMA_VERSION,
            frame_strategy=request.strategy,
            image_count=len(request.frames),
            image_sizes_bytes=[len(f.bytes) for f in request.frames],
            total_image_bytes=sum(len(f.bytes) for f in request.frames),
            mime_types=[f.mime_type for f in request.frames],
            capture_config_version=request.capture_config_version,
            quality_config_version=request.quality_config_version,
        )

    def _log_response_received(
        self,
        request: ExperimentEvaluateRequest,
        response: VisionEvaluationResponse,
        experiment_id: str,
        total_latency_ms: int,
    ) -> None:
        if not self._settings.vlm_experiment_logging_enabled:
            return
        assessment = response.assessment
        usage = response.usage
        logger.info(
            "vlm_experiment_response_received",
            experiment_id=experiment_id,
            provider=request.provider,
            model=response.model,
            classification=assessment.classification,
            attack_medium=assessment.attack_medium,
            self_reported_confidence=assessment.self_reported_confidence,
            evidence_codes=list(assessment.evidence_codes),
            subject_count=assessment.subject_count,
            secondary_person_state=assessment.secondary_person_state,
            provider_latency_ms=response.provider_latency_ms,
            total_latency_ms=total_latency_ms,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            schema_validation="success",
        )

    def _log_failed(
        self,
        request: ExperimentEvaluateRequest,
        provider: VisionProvider,
        experiment_id: str,
        error_code: VlmErrorCode,
        latency_ms: int,
        retry_count: int,
    ) -> None:
        if not self._settings.vlm_experiment_logging_enabled:
            return
        logger.info(
            "vlm_experiment_failed",
            experiment_id=experiment_id,
            provider=request.provider,
            model=provider.info.model_id,
            error_code=error_code.value,
            retry_count=retry_count,
            latency_ms=latency_ms,
        )

    async def evaluate(self, request: ExperimentEvaluateRequest) -> ExperimentResult:
        self.ensure_available()
        self._validate_strategy(request.strategy, len(request.frames))
        experiment_id = uuid.uuid4().hex

        provider = self._provider_factory(self._settings, request.provider)
        self._check_capabilities(provider, request)
        self._log_request_started(request, provider, experiment_id)

        vision_request = VisionEvaluationRequest(
            images=request.frames,
            prompt_id=PROMPT_ID,
            prompt_version=PROMPT_VERSION,
            schema_version=VLM_SCHEMA_VERSION,
            temperature=0.0,
            provider_options={
                "frame_strategy": request.strategy,
                "mock_behavior": request.mock_behavior,
            },
        )

        started = time.perf_counter()
        error_code: VlmErrorCode | None = None
        try:
            response = await provider.evaluate(vision_request)
            assessment = response.assessment
        except VlmError as exc:
            error_code = exc.code
            duration = time.perf_counter() - started
            latency_ms = int(duration * 1000)
            record_vlm_evaluation(request.provider, "error", duration, error_type=exc.code.value)
            logger.info(
                "vlm_evaluation_completed",
                provider=request.provider,
                model=provider.info.model_id,
                prompt_version=PROMPT_VERSION,
                image_count=len(request.frames),
                latency_ms=latency_ms,
                error=exc.code.value,
            )
            self._log_failed(
                request,
                provider,
                experiment_id,
                error_code,
                latency_ms,
                retry_count=0,
            )
            return ExperimentResult(
                provider=request.provider,
                model=provider.info.model_id,
                frame_strategy=request.strategy,
                image_count=len(request.frames),
                experiment_id=experiment_id,
                error=error_code,
            )

        duration = time.perf_counter() - started
        latency_ms = int(duration * 1000)
        record_vlm_evaluation(request.provider, assessment.classification.value, duration)
        logger.info(
            "vlm_evaluation_completed",
            provider=request.provider,
            model=provider.info.model_id,
            prompt_version=PROMPT_VERSION,
            image_count=len(request.frames),
            classification=assessment.classification.value,
            subject_count=assessment.subject_count.value,
            secondary_person_state=assessment.secondary_person_state.value,
            latency_ms=latency_ms,
        )
        self._log_response_received(request, response, experiment_id, latency_ms)

        return ExperimentResult(
            provider=request.provider,
            model=provider.info.model_id,
            frame_strategy=request.strategy,
            image_count=len(request.frames),
            experiment_id=experiment_id,
            classification=assessment.classification.value,
            attack_medium=assessment.attack_medium.value,
            self_reported_confidence=assessment.self_reported_confidence,
            evidence_codes=list(assessment.evidence_codes),
            subject_count=assessment.subject_count.value,
            secondary_person_state=assessment.secondary_person_state.value,
            latency_ms=latency_ms,
        )
