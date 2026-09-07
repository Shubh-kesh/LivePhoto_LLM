"""Backend portrait processing (M5.7)."""

from app.portrait.errors import (
    PortraitErrorCode,
    PortraitProcessingError,
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
    "MATTE_REFINEMENT_VERSION",
    "PROCESSOR_VERSION",
    "FakePortraitSegmentation",
    "OnnxPortraitSegmentation",
    "PortraitErrorCode",
    "PortraitProcessingError",
    "PortraitProcessingResult",
    "PortraitProcessor",
    "SegmentationProvider",
    "refine_matte",
]
