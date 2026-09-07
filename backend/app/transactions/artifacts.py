"""Artifact references for transaction-scoped filesystem storage (M5.7 §14-16).

Artifact references are an internal, non-database convention for referring to files inside a
transaction directory. They never expose absolute server paths to callers/frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactType(StrEnum):
    """Persisted transaction artifact kinds (M5.7 §16)."""

    SELECTED_ORIGINAL_CAPTURE = "SELECTED_ORIGINAL_CAPTURE"
    VLM_RESULT = "VLM_RESULT"
    PROCESSED_PORTRAIT = "PROCESSED_PORTRAIT"
    PORTRAIT_PROCESSING_RESULT = "PORTRAIT_PROCESSING_RESULT"

    @property
    def directory(self) -> str:
        return {
            ArtifactType.SELECTED_ORIGINAL_CAPTURE: "capture",
            ArtifactType.VLM_RESULT: "vlm",
            ArtifactType.PROCESSED_PORTRAIT: "portrait",
            ArtifactType.PORTRAIT_PROCESSING_RESULT: "portrait",
        }[self]


#: Relative paths (transaction-relative) for canonical artifacts.
ARTIFACT_RELATIVE_PATHS: dict[ArtifactType, str] = {
    ArtifactType.SELECTED_ORIGINAL_CAPTURE: "capture/selected-original.jpg",
    ArtifactType.VLM_RESULT: "vlm/result.json",
    ArtifactType.PROCESSED_PORTRAIT: "portrait/processed.jpg",
    ArtifactType.PORTRAIT_PROCESSING_RESULT: "portrait/processing.json",
}


@dataclass(frozen=True)
class ArtifactReference:
    """Reference to a persisted artifact inside a transaction directory (M5.7 §15)."""

    transaction_id: str
    artifact_type: ArtifactType
    relative_path: str
    content_type: str = ""
    size_bytes: int = 0
    sha256: str = ""
