"""Liveness decision outcome (M0 §10, M1 §25).

These four outcomes are the bank-relevant semantics produced by the future policy engine. They are
distinct from ``SessionState``: multiple decisions may exist across retries/reviews while a session
has exactly one lifecycle.

- ``PASS``    evidence strongly supports a genuine live user
- ``RETRY``   capture may be valid but quality prevents reliable evaluation
- ``REVIEW``  conflicting/suspicious evidence; business policy permits manual review
- ``FAIL``    strong presentation-attack/tampering/invalid-session evidence
"""

from __future__ import annotations

import enum


class DecisionOutcome(enum.StrEnum):
    PASS = "PASS"
    RETRY = "RETRY"
    REVIEW = "REVIEW"
    FAIL = "FAIL"
