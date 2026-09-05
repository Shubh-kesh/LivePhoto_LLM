"""Validator seam tests (M1 §27-28)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.domain.validation import ValidatorHealth, ValidatorResult, ValidatorResultStatus
from app.validators import Validator, ValidatorInput


class _FakeInput:
    frame_references: Sequence[str] = ("frame-ref-1", "frame-ref-2")
    metadata: Mapping[str, object] | None = None


class _FakeValidator:
    name = "fake_quality"
    version = "0.1.0"

    def validate(self, input: ValidatorInput) -> ValidatorResult:
        return ValidatorResult(
            validator_name=self.name,
            validator_version=self.version,
            result=ValidatorResultStatus.PASS,
        )

    def health(self) -> ValidatorHealth:
        return ValidatorHealth()


def test_fake_validator_conforms_to_protocol() -> None:
    assert isinstance(_FakeValidator(), Validator)


def test_validator_result_round_trip() -> None:
    validator = _FakeValidator()
    result = validator.validate(_FakeInput())
    assert result.validator_name == "fake_quality"
    assert result.result is ValidatorResultStatus.PASS
    assert validator.health().status is ValidatorResultStatus.PASS


def test_input_contract_holds_frame_references_only() -> None:
    assert _FakeInput().frame_references == ("frame-ref-1", "frame-ref-2")
