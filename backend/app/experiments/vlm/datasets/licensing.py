"""Dataset licensing decision helpers (M5 §7-12, §107-108; continuation §3).

M5 public-dataset use purpose = NON_COMMERCIAL_POC_RESEARCH. The coding agent does NOT declare
"legally approved"; it reports "license appears compatible based on published terms" or "requires
organization/legal confirmation". If no dataset clearly supports the intended POC use, the gate is
BLOCKED.
"""

from __future__ import annotations

from app.experiments.vlm.datasets.registry import (
    DatasetDescriptor,
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
                download_source=None,
                mirror_source=None,
                license_state=LicenseState.UNCLEAR,
                license_note="Unknown dataset; LICENSE_REVIEW_REQUIRED.",
            ),
            "LICENSE_REVIEW_REQUIRED — dataset not in the known registry.",
        )

    if is_usable_for_external_vlm(descriptor):
        return descriptor, (
            "license appears compatible based on published terms for NON_COMMERCIAL POC/RESEARCH "
            "use, including external VLM processing (attribution required; not for commercial use)."
        )
    if descriptor.license_state == LicenseState.ALLOWED_FOR_LOCAL_ONLY:
        return descriptor, (
            "ALLOWED_FOR_LOCAL_ONLY — non-commercial research use appears permitted locally, but "
            "external VLM processing is NOT allowed; keep the data local for POC."
        )
    if descriptor.license_state == LicenseState.REQUIRES_APPROVAL:
        return descriptor, (
            "REQUIRES_APPROVAL — an EULA / signed agreement / owner permission is required before "
            "use; do not bypass via a mirror."
        )
    if descriptor.license_state == LicenseState.NOT_ALLOWED:
        return descriptor, (
            "NOT_ALLOWED — terms clearly prohibit the intended use under this purpose."
        )
    return descriptor, (
        "UNCLEAR — published terms are insufficient to determine whether external-provider "
        "processing is acceptable; do not use until confirmed by organization/legal."
    )


def require_usable_dataset(name: str) -> DatasetDescriptor:
    """Raise DatasetLicenseError unless the dataset is clearly usable for external-VLM POC use."""
    descriptor, decision = evaluate_dataset(name)
    if not is_usable_for_external_vlm(descriptor):
        raise DatasetLicenseError(
            f"dataset '{name}' is not usable for external-VLM POC use: {decision}"
        )
    return descriptor
