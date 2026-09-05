"""Normalized validator output contract (M0 VALIDATION_PIPELINE §3, M1 §27).

Score concepts are deliberately kept distinct (M0 P12):

- ``raw_score``          model-native output (units/meaning vary per model)
- ``calibrated_score``   post-calibration probability for the validator's declared outcome
- ``threshold``          operating point applied (versioned)
- business ``risk_score`` is NOT represented here — it is computed later by the policy engine

Only ``validator_name`` and ``validator_version`` are required; a validator that legitimately
cannot produce a score leaves the optional fields unset.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from app.domain.reason import ReasonCode


class ValidatorResultStatus(enum.StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class ValidatorResult(BaseModel):
    validator_name: str
    validator_version: str
    result: ValidatorResultStatus
    reason_codes: list[ReasonCode] = Field(default_factory=list)

    raw_score: float | None = None
    calibrated_score: float | None = None
    threshold: float | None = None
    latency_ms: int | None = None
    model_version: str | None = None
    configuration_version: str | None = None


class ValidatorHealth(BaseModel):
    status: ValidatorResultStatus = ValidatorResultStatus.PASS
    detail: str | None = None
