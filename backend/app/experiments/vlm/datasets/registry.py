"""Dataset registry (M5 §14-15, §18).

Known public PAD datasets and their license/usage posture. Registry entries record published
license terms; code never silently redefines a license status. This list is exploratory and does
NOT authorize any download or external-provider submission.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class LicenseState(StrEnum):
    ALLOWED = "ALLOWED"
    NOT_ALLOWED = "NOT_ALLOWED"
    UNCLEAR = "UNCLEAR"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class ExternalProcessingStatus(StrEnum):
    ALLOWED = "ALLOWED"
    NOT_ALLOWED = "NOT_ALLOWED"
    UNCLEAR = "UNCLEAR"


@dataclass(frozen=True)
class DatasetDescriptor:
    name: str
    version: str
    source: str
    mirror_source: str | None
    license_state: LicenseState
    license_note: str
    classes: tuple[str, ...]
    external_vlm_processing: ExternalProcessingStatus
    access_restrictions: str
    image_or_video: Literal["image", "video"]
    research_only: bool = False


#: Exploration records. Official terms for these datasets are non-commercial research and/or
#: require institutional agreements, so they are NOT selected for external-provider benchmarking
#: without explicit approval (M5 §8, §11, §108).
KNOWN_DATASETS: tuple[DatasetDescriptor, ...] = (
    DatasetDescriptor(
        name="celebA-spoof",
        version="1",
        source="GitHub open-the-loop/celebA-spoof",
        mirror_source=None,
        license_state=LicenseState.NOT_ALLOWED,
        license_note="Terms target research/non-commercial use; commercial banking use requires "
        "explicit confirmation. See upstream repository license/terms.",
        classes=("LIVE", "SCREEN_MOBILE", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.UNCLEAR,
        access_restrictions="Research terms; attribution expected",
        image_or_video="video",
        research_only=True,
    ),
    DatasetDescriptor(
        name="replay-attack",
        version="v1",
        source="Idiap Research Institute",
        mirror_source=None,
        license_state=LicenseState.NOT_ALLOWED,
        license_note="Non-commercial research; requires a signed Idiap agreement.",
        classes=("LIVE", "SCREEN_MOBILE", "SCREEN_LAPTOP", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Signed agreement required",
        image_or_video="video",
        research_only=True,
    ),
    DatasetDescriptor(
        name="replay-mobile",
        version="v1",
        source="Idiap Research Institute",
        mirror_source=None,
        license_state=LicenseState.NOT_ALLOWED,
        license_note="Non-commercial research; requires a signed Idiap agreement.",
        classes=("LIVE", "SCREEN_MOBILE", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Signed agreement required",
        image_or_video="video",
        research_only=True,
    ),
    DatasetDescriptor(
        name="oulu-npu",
        version="1",
        source="University of Oulu",
        mirror_source=None,
        license_state=LicenseState.NOT_ALLOWED,
        license_note="Non-commercial research; requires acceptance of OULU-NPU terms.",
        classes=("LIVE", "SCREEN_MOBILE", "SCREEN_TABLET", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Agreement/terms required",
        image_or_video="video",
        research_only=True,
    ),
    DatasetDescriptor(
        name="siw",
        version="v1",
        source="Michigan State University (MSU) SiW",
        mirror_source=None,
        license_state=LicenseState.NOT_ALLOWED,
        license_note="Non-commercial research terms.",
        classes=("LIVE", "SCREEN_MOBILE", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Research terms",
        image_or_video="video",
        research_only=True,
    ),
    DatasetDescriptor(
        name="axon-sample",
        version="unknown",
        source="Axon sample/public sets",
        mirror_source=None,
        license_state=LicenseState.UNCLEAR,
        license_note="Published sample availability does not by itself authorize commercial or "
        "third-party-processing use; treat as LICENSE_REVIEW_REQUIRED.",
        classes=("LIVE", "SCREEN_MOBILE", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.UNCLEAR,
        access_restrictions="Unclear",
        image_or_video="image",
    ),
)


def registry() -> dict[str, DatasetDescriptor]:
    return {entry.name: entry for entry in KNOWN_DATASETS}


def find_dataset(name: str) -> DatasetDescriptor | None:
    return registry().get(name)


def is_usable_for_external_vlm(descriptor: DatasetDescriptor) -> bool:
    """A dataset is usable for real external-provider benchmarking only when both the license
    state and the external-processing status are ALLOWED (M5 §8, §12)."""
    return (
        descriptor.license_state == LicenseState.ALLOWED
        and descriptor.external_vlm_processing == ExternalProcessingStatus.ALLOWED
    )


def review_required(descriptor: DatasetDescriptor) -> bool:
    return descriptor.license_state in (LicenseState.UNCLEAR, LicenseState.REQUIRES_APPROVAL)
