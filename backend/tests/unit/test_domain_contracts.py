"""Domain contract invariants (M1 §24-27, §54)."""

from __future__ import annotations

from app.domain import (
    NON_TERMINAL_SESSION_STATES,
    TERMINAL_SESSION_STATES,
    DecisionOutcome,
    ReasonCode,
    SessionState,
    ValidatorResult,
    ValidatorResultStatus,
    is_terminal_session_state,
)


def test_session_state_enum_members() -> None:
    assert SessionState.CREATED.value == "CREATED"
    assert SessionState.ACTIVE.value == "ACTIVE"
    assert SessionState.CAPTURE_IN_PROGRESS.value == "CAPTURE_IN_PROGRESS"
    assert SessionState.VALIDATING.value == "VALIDATING"
    assert SessionState.PASS.value == "PASS"
    assert SessionState.RETRY.value == "RETRY"
    assert SessionState.REVIEW.value == "REVIEW"
    assert SessionState.FAIL.value == "FAIL"
    assert SessionState.EXPIRED.value == "EXPIRED"
    assert SessionState.CANCELLED.value == "CANCELLED"


def test_session_state_partition_is_exhaustive() -> None:
    all_states = set(SessionState)
    assert all_states == TERMINAL_SESSION_STATES | NON_TERMINAL_SESSION_STATES
    assert frozenset() == TERMINAL_SESSION_STATES & NON_TERMINAL_SESSION_STATES


def test_terminal_and_non_terminal_membership() -> None:
    assert is_terminal_session_state(SessionState.PASS)
    assert is_terminal_session_state(SessionState.REVIEW)
    assert is_terminal_session_state(SessionState.FAIL)
    assert is_terminal_session_state(SessionState.EXPIRED)
    assert is_terminal_session_state(SessionState.CANCELLED)
    assert not is_terminal_session_state(SessionState.CREATED)
    assert not is_terminal_session_state(SessionState.RETRY)
    assert not is_terminal_session_state(SessionState.VALIDATING)


def test_decision_outcome_is_distinct_from_session_state() -> None:
    # Same-looking names are distinct enum types; a decision outcome is not a session state.
    assert DecisionOutcome.PASS is not SessionState.PASS
    assert set(DecisionOutcome) == {
        DecisionOutcome.PASS,
        DecisionOutcome.RETRY,
        DecisionOutcome.REVIEW,
        DecisionOutcome.FAIL,
    }


def test_reason_code_vocabulary_required_codes_present() -> None:
    required = {
        "NO_FACE",
        "MULTIPLE_FACES",
        "FACE_TOO_SMALL",
        "BLURRED",
        "UNDEREXPOSED",
        "OVEREXPOSED",
        "FACE_OCCLUDED",
        "SCREEN_REPLAY_SUSPECTED",
        "PRINT_ATTACK_SUSPECTED",
        "PASSIVE_PAD_FAILED",
        "UNCERTAIN",
        "INTERNAL_VALIDATION_ERROR",
    }
    assert required <= {code.value for code in ReasonCode}


def test_validator_result_keeps_score_concepts_distinct() -> None:
    result = ValidatorResult(
        validator_name="device_detector",
        validator_version="1.0.0",
        result=ValidatorResultStatus.PASS,
        raw_score=0.91,
        calibrated_score=0.87,
        threshold=0.80,
        reason_codes=[],
    )
    # raw_score, calibrated_score and threshold are separate fields and never aliased.
    assert result.raw_score == 0.91
    assert result.calibrated_score == 0.87
    assert result.threshold == 0.80
    assert result.raw_score != result.calibrated_score


def test_validator_result_optional_fields_default_to_none() -> None:
    result = ValidatorResult(
        validator_name="x", validator_version="1.0.0", result=ValidatorResultStatus.SKIPPED
    )
    assert result.raw_score is None
    assert result.calibrated_score is None
    assert result.threshold is None
    assert result.model_version is None
    assert result.configuration_version is None
    assert result.latency_ms is None


def test_validator_result_serializes_reason_codes_as_strings() -> None:
    result = ValidatorResult(
        validator_name="x",
        validator_version="1.0.0",
        result=ValidatorResultStatus.FAIL,
        reason_codes=[ReasonCode.SCREEN_REPLAY_SUSPECTED, ReasonCode.PASSIVE_PAD_FAILED],
    )
    data = result.model_dump()
    assert data["reason_codes"] == ["SCREEN_REPLAY_SUSPECTED", "PASSIVE_PAD_FAILED"]
