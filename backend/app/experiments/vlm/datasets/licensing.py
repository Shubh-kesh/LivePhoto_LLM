"""Dataset licensing decision helpers (M5 §7-12, §107-108).

The coding agent does NOT declare "legally approved" unless documented approval exists. We use
"license appears compatible based on published terms" or "requires organization/legal
confirmation". If no dataset clearly supports the intended usage, the gate is BLOCKED.
"""

from __future__ import annotations

from app.experiments.vlm.datasets.registry import (
    DatasetDescriptor,
    ExternalProcessingStatus,
    LicenseState,
    is_usable_for_external_vlm,
    registry,
)


class DatasetLicenseError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def evaluate_dataset(name: str) -> tuple[DatasetDescriptor, str]:
    """Return (descriptor, decision text) for a dataset name without selecting it."""
    descriptor = registry().get(name)
    if descriptor is None:
        return (
            DatasetDescriptor(
                name=name,
                version="unknown",
                source="unknown",
                mirror_source=None,
                license_state=LicenseState.UNCLEAR,
                license_note="Unknown dataset; LICENSE_REVIEW_REQUIRED.",
                classes=(),
                external_vlm_processing=ExternalProcessingStatus.UNCLEAR,
                access_restrictions="Unclear",
                image_or_video="image",
            ),
            "LICENSE_REVIEW_REQUIRED — dataset not in the known registry.",
        )

    if is_usable_for_external_vlm(descriptor):
        return descriptor, "license appears compatible based on published terms"
    if descriptor.license_state == LicenseState.NOT_ALLOWED:
        return descriptor, (
            "NOT_ALLOWED — official terms are non-commercial research and/or require a signed "
            "agreement; not usable for this commercial project or external-provider processing "
            "without approval."
        )
    return descriptor, (
        "LICENSE_REVIEW_REQUIRED — usage rights are unclear; do not use until confirmed by "
        "organization/legal."
    )


def require_usable_dataset(name: str) -> DatasetDescriptor:
    """Raise DatasetLicenseError unless the dataset is clearly usable for external-VLM use."""
    descriptor, decision = evaluate_dataset(name)
    if not is_usable_for_external_vlm(descriptor):
        raise DatasetLicenseError(
            f"dataset '{name}' is not usable for external-VLM use: {decision}"
        )
    return descriptor
