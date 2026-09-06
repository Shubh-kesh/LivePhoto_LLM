"""M4 experiments package (development-only VLM baseline)."""

from app.experiments.vlm.frame_selection import (
    FRAME_STRATEGIES,
    expected_frame_count,
    select_single_frame,
    select_temporal_triad,
)
from app.experiments.vlm.service import (
    ExperimentEvaluateRequest,
    ExperimentResult,
    VlmEvaluationService,
)

__all__ = [
    "FRAME_STRATEGIES",
    "ExperimentEvaluateRequest",
    "ExperimentResult",
    "VlmEvaluationService",
    "expected_frame_count",
    "select_single_frame",
    "select_temporal_triad",
]
