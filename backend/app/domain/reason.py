"""Deterministic reason-code vocabulary (M0 VALIDATION_PIPELINE §9, M1 §26).

Reason codes are stable, machine-readable application concepts. They are the vocabulary used by
future validators and the policy engine; natural-language model explanations are never used as
reason codes. New codes must be added deliberately to this enum and to the registry in
``docs/VALIDATION_PIPELINE.md``.
"""

from __future__ import annotations

import enum


class ReasonCode(enum.StrEnum):
    # Face / framing
    NO_FACE = "NO_FACE"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    FACE_TOO_SMALL = "FACE_TOO_SMALL"
    FACE_NOT_CENTERED = "FACE_NOT_CENTERED"
    FACE_OCCLUDED = "FACE_OCCLUDED"

    # Quality
    BLURRED = "BLURRED"
    UNDEREXPOSED = "UNDEREXPOSED"
    OVEREXPOSED = "OVEREXPOSED"
    IMAGE_QUALITY_FAILED = "IMAGE_QUALITY_FAILED"

    # Attack signals
    SCREEN_REPLAY_SUSPECTED = "SCREEN_REPLAY_SUSPECTED"
    PRINT_ATTACK_SUSPECTED = "PRINT_ATTACK_SUSPECTED"
    PASSIVE_PAD_FAILED = "PASSIVE_PAD_FAILED"
    PAD_SCORE_BELOW_THRESHOLD = "PAD_SCORE_BELOW_THRESHOLD"

    # Model / fusion
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
    UNCERTAIN = "UNCERTAIN"

    # Operational
    VALIDATOR_TIMEOUT = "VALIDATOR_TIMEOUT"
    VALIDATOR_ERROR = "VALIDATOR_ERROR"
    CAPTURE_TOO_FEW_FRAMES = "CAPTURE_TOO_FEW_FRAMES"

    # Session / security
    SESSION_INVALID = "SESSION_INVALID"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    TOKEN_REPLAY_DETECTED = "TOKEN_REPLAY_DETECTED"
    INVALID_REDIRECT = "INVALID_REDIRECT"
    RATE_LIMIT_TRIGGERED = "RATE_LIMIT_TRIGGERED"

    # Internal
    INTERNAL_VALIDATION_ERROR = "INTERNAL_VALIDATION_ERROR"
