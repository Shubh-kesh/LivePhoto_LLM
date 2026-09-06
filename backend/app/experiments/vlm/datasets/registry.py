"""Dataset registry (M5 §14-15, §18; continuation: NON_COMMERCIAL_POC_RESEARCH purpose).

M5 public-dataset use purpose = NON_COMMERCIAL POC / RESEARCH ONLY. Public datasets are used for a
non-commercial POC/research evaluation and NOT for production, sale, redistribution, commercial
training, production model fine-tuning, or production customer data. A future commercial use
requires a completely separate license/governance review (continuation §1, §48).

Registry entries record published license terms under this purpose; code never silently redefines
a license status. This list is exploratory and does NOT authorize any download or external-provider
submission on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class LicenseState(StrEnum):
    ALLOWED_FOR_POC = "ALLOWED_FOR_POC"
    ALLOWED_FOR_LOCAL_ONLY = "ALLOWED_FOR_LOCAL_ONLY"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    NOT_ALLOWED = "NOT_ALLOWED"
    UNCLEAR = "UNCLEAR"


class ExternalProcessingStatus(StrEnum):
    ALLOWED = "ALLOWED"
    NOT_ALLOWED = "NOT_ALLOWED"
    UNCLEAR = "UNCLEAR"


#: M5 dataset-use purpose (fixed for M5; NOT a commercial authorization).
USAGE_PURPOSE = "NON_COMMERCIAL_POC_RESEARCH"

REVIEW_DATE = "2026-09-06"


@dataclass(frozen=True)
class DatasetDescriptor:
    name: str
    version: str
    source: str
    download_source: str | None
    mirror_source: str | None
    license_state: LicenseState
    license_note: str
    license_url_reference: str | None = None
    classes: tuple[str, ...] = ()
    external_vlm_processing: ExternalProcessingStatus = ExternalProcessingStatus.UNCLEAR
    access_restrictions: str = "See published terms"
    image_or_video: Literal["image", "video", "both"] = "image"
    usage_purpose: str = USAGE_PURPOSE
    review_date: str = REVIEW_DATE
    notes: str = ""


#: Exploration records, reassessed for NON_COMMERCIAL_POC_RESEARCH use.
KNOWN_DATASETS: tuple[DatasetDescriptor, ...] = (
    DatasetDescriptor(
        name="axon-face-anti-spoofing-sample",
        version="sample-1",
        source="Axon Labs (AxonData) — official Hugging Face publication",
        download_source="https://huggingface.co/datasets/AxonData/face-anti-spoofing-dataset",
        mirror_source="Kaggle axondata/face-anti-spoofing-dataset",
        license_state=LicenseState.ALLOWED_FOR_POC,
        license_note=(
            "Published under CC BY-NC 4.0. For NON_COMMERCIAL_POC_RESEARCH use with "
            "non-commercial evaluation including sending a selected subset to an "
            "external VLM is "
            "reasonably permitted (processing is not redistribution). NOT for "
            "production/commercial use; a new license review is required for commercial."
        ),
        license_url_reference="https://huggingface.co/datasets/AxonData/face-anti-spoofing-dataset",
        classes=("LIVE", "SCREEN_MOBILE", "SCREEN_DISPLAY"),
        external_vlm_processing=ExternalProcessingStatus.ALLOWED,
        access_restrictions="Non-commercial only; attribution required",
        image_or_video="both",
        notes="Sample subset; full commercial dataset requires separate licensing.",
    ),
    DatasetDescriptor(
        name="celebA-spoof",
        version="1",
        source="GitHub open-the-loop/celebA-spoof",
        download_source="GitHub / official mirrors",
        mirror_source=None,
        license_state=LicenseState.ALLOWED_FOR_LOCAL_ONLY,
        license_note=(
            "Research/non-commercial use appears permitted, but copying/distribution and "
            "third-party processing terms are restrictive/uncertain. Keep local-only; do NOT "
            "submit images to an external VLM without explicit approval."
        ),
        classes=("LIVE", "SCREEN_MOBILE", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Research; redistribution/third-party processing restricted/uncertain",
        image_or_video="video",
        notes="Treat as local-only for M5 POC.",
    ),
    DatasetDescriptor(
        name="replay-attack",
        version="v1",
        source="Idiap Research Institute",
        download_source="Idiap (agreement-gated)",
        mirror_source=None,
        license_state=LicenseState.REQUIRES_APPROVAL,
        license_note=(
            "Non-commercial research; requires a signed Idiap agreement before access/use."
        ),
        classes=("LIVE", "SCREEN_MOBILE", "SCREEN_LAPTOP", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Signed agreement required",
        image_or_video="video",
    ),
    DatasetDescriptor(
        name="replay-mobile",
        version="v1",
        source="Idiap Research Institute",
        download_source="Idiap (agreement-gated)",
        mirror_source=None,
        license_state=LicenseState.REQUIRES_APPROVAL,
        license_note="Non-commercial research; requires a signed Idiap agreement.",
        classes=("LIVE", "SCREEN_MOBILE", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Signed agreement required",
        image_or_video="video",
    ),
    DatasetDescriptor(
        name="oulu-npu",
        version="1",
        source="University of Oulu",
        download_source="OULU-NPU official (terms-gated)",
        mirror_source=None,
        license_state=LicenseState.REQUIRES_APPROVAL,
        license_note=(
            "Requires acceptance of OULU-NPU terms (EULA/agreement); do not bypass via mirror."
        ),
        classes=("LIVE", "SCREEN_MOBILE", "SCREEN_TABLET", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Agreement/terms required",
        image_or_video="video",
    ),
    DatasetDescriptor(
        name="siw",
        version="v1",
        source="Michigan State University (MSU) SiW",
        download_source="MSU (terms-gated)",
        mirror_source=None,
        license_state=LicenseState.REQUIRES_APPROVAL,
        license_note="Non-commercial research terms; institutional access required.",
        classes=("LIVE", "SCREEN_MOBILE", "PRINT_PHOTO"),
        external_vlm_processing=ExternalProcessingStatus.NOT_ALLOWED,
        access_restrictions="Research terms",
        image_or_video="video",
    ),
)


def registry() -> dict[str, DatasetDescriptor]:
    return {entry.name: entry for entry in KNOWN_DATASETS}


def find_dataset(name: str) -> DatasetDescriptor | None:
    return registry().get(name)


def is_usable_for_external_vlm(descriptor: DatasetDescriptor) -> bool:
    """A dataset may be submitted to an external VLM for the POC only when the license state is
    ALLOWED_FOR_POC AND the external-processing status is ALLOWED (continuation §3)."""
    return (
        descriptor.license_state == LicenseState.ALLOWED_FOR_POC
        and descriptor.external_vlm_processing == ExternalProcessingStatus.ALLOWED
    )


def is_usable_for_local_only(descriptor: DatasetDescriptor) -> bool:
    """Dataset may be used for local non-commercial research but not submitted externally."""
    return descriptor.license_state in (
        LicenseState.ALLOWED_FOR_POC,
        LicenseState.ALLOWED_FOR_LOCAL_ONLY,
    )


def review_required(descriptor: DatasetDescriptor) -> bool:
    return descriptor.license_state in (LicenseState.UNCLEAR, LicenseState.REQUIRES_APPROVAL)
