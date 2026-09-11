"""Backend portrait processing (M5.7)."""

from app.portrait.errors import (
    RETRYABLE_PORTRAIT_CODES,
    PortraitErrorCode,
    PortraitProcessingError,
)
from app.portrait.integrity import (
    MATTE_INTEGRITY_VERSION,
    MatteIntegrity,
    parse_normalized_face_box,
    validate_face_box_values,
    validate_portrait_matte,
)
from app.portrait.matte import MATTE_REFINEMENT_VERSION, refine_matte
from app.portrait.processor import (
    PROCESSOR_VERSION,
    PortraitProcessingResult,
    PortraitProcessor,
)
from app.portrait.segmentation import (
    FakePortraitSegmentation,
    OnnxPortraitSegmentation,
    SegmentationProvider,
)

__all__ = [
    "MATTE_INTEGRITY_VERSION",
    "MATTE_REFINEMENT_VERSION",
    "PROCESSOR_VERSION",
    "RETRYABLE_PORTRAIT_CODES",
    "FakePortraitSegmentation",
    "MatteIntegrity",
    "OnnxPortraitSegmentation",
    "PortraitErrorCode",
    "PortraitProcessingError",
    "PortraitProcessingResult",
    "PortraitProcessor",
    "SegmentationProvider",
    "parse_normalized_face_box",
    "refine_matte",
    "validate_face_box_values",
    "validate_portrait_matte",
]
