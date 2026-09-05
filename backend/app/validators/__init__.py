"""Liveness-validation seam (M0 ADR-004, M1 §27-28).

No validators are implemented in M1. This package defines the seam future validators conform to:
a ``Validator`` protocol returning the normalized ``ValidatorResult``. The scoring/policy engine
(also future) consumes these results; validators themselves never make the business decision.

No model (RetinaFace/YOLO/OpenCV/etc.) is selected in M1; selection is benchmark-driven in M4-M7.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from app.domain.validation import ValidatorHealth, ValidatorResult


@runtime_checkable
class ValidatorInput(Protocol):
    """Minimal input contract for validators (frame references, not raw bytes).

    Concrete validators define their own richer input models later; this is the shared floor.
    """

    frame_references: Sequence[str]
    metadata: Mapping[str, Any] | None


@runtime_checkable
class Validator(Protocol):
    """A replaceable validation layer producing evidence, never a banking decision."""

    name: str
    version: str

    def validate(self, input: ValidatorInput) -> ValidatorResult: ...
    def health(self) -> ValidatorHealth: ...


__all__ = ["Validator", "ValidatorHealth", "ValidatorInput", "ValidatorResult"]
