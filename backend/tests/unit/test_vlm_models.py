"""VLM normalized-model tests (M4 §52-55, §129)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.providers.vision import (
    AttackMedium,
    EvidenceCode,
    VlmAssessment,
    VlmClassification,
)
from app.providers.vision.base import parse_assessment
from app.providers.vision.errors import VlmError, VlmErrorCode


def test_assessment_accepts_valid_live_result() -> None:
    assessment = VlmAssessment(
        classification=VlmClassification.LIVE,
        attack_medium=AttackMedium.NONE,
        self_reported_confidence=0.95,
        evidence_codes=[EvidenceCode.ENVIRONMENT_CONSISTENT_WITH_LIVE],
    )
    assert assessment.classification is VlmClassification.LIVE
    assert assessment.self_reported_confidence == 0.95


def test_assessment_rejects_invalid_classification() -> None:
    with pytest.raises(ValidationError):
        VlmAssessment(
            classification="SPOOF",  # type: ignore[arg-type]
            attack_medium=AttackMedium.NONE,
            self_reported_confidence=0.5,
        )


def test_assessment_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        VlmAssessment(
            classification=VlmClassification.LIVE,
            attack_medium=AttackMedium.NONE,
            self_reported_confidence=1.5,
        )


def test_assessment_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        VlmAssessment.model_validate(
            {
                "classification": "LIVE",
                "attack_medium": "NONE",
                "self_reported_confidence": 0.9,
                "evidence_codes": [],
                "liveness_score": 0.99,
            }
        )


def test_assessment_retains_unknown_evidence_codes() -> None:
    # Real providers emit codes beyond the controlled enum; they are retained as observations,
    # never treated as ground truth (M4 §38).
    assessment = VlmAssessment.model_validate(
        {
            "classification": "QUALITY_FAILURE",
            "attack_medium": "NONE",
            "self_reported_confidence": 0.9,
            "evidence_codes": ["BLANK_FRAME", "NO_FACE_DETECTED"],
        }
    )
    assert assessment.evidence_codes == ["BLANK_FRAME", "NO_FACE_DETECTED"]


def test_assessment_rejects_excessive_evidence_codes() -> None:
    with pytest.raises(ValidationError):
        VlmAssessment.model_validate(
            {
                "classification": "LIVE",
                "attack_medium": "NONE",
                "self_reported_confidence": 0.9,
                "evidence_codes": [f"code-{i}" for i in range(30)],
            }
        )


def test_parse_assessment_validates_strictly() -> None:
    text = (
        '{"classification": "SCREEN_REPLAY", "attack_medium": "MOBILE_SCREEN", '
        '"self_reported_confidence": 0.86, "evidence_codes": ["DEVICE_BORDER_VISIBLE"]}'
    )
    assessment = parse_assessment(text)
    assert assessment.classification is VlmClassification.SCREEN_REPLAY


def test_parse_assessment_invalid_json_raises_schema_error() -> None:
    with pytest.raises(VlmError) as exc:
        parse_assessment('{"classification": ')
    assert exc.value.code is VlmErrorCode.SCHEMA_VALIDATION_ERROR


def test_parse_assessment_schema_violation_raises_schema_error() -> None:
    with pytest.raises(VlmError):
        parse_assessment(
            '{"classification": "NOT_A_CLASS", "attack_medium": "NONE", '
            '"self_reported_confidence": 0.5, "evidence_codes": []}'
        )


def test_parse_assessment_handles_code_fence_wrapper() -> None:
    text = (
        "```json\n"
        '{"classification": "PRINT_ATTACK", "attack_medium": "PRINT_PHOTO", '
        '"self_reported_confidence": 0.8, "evidence_codes": ["PAPER_TEXTURE"]}\n'
        "```"
    )
    assessment = parse_assessment(text)
    assert assessment.classification is VlmClassification.PRINT_ATTACK
