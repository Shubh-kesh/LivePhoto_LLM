"""Canonical decision record (M5.8 §17).

Production Submit requires a persisted canonical ``DecisionOutcome.PASS`` plus a processed portrait
with valid artifact SHA-256. This record is the authoritative authorization boundary; the
experimental VLM result (``vlm/result.json``) is never consulted for submission.

In M5.8 the only writer of a canonical decision is the strictly test-only dev endpoint (registered
only when ``app_env in {local,test,development}`` AND ``decision_test_writer_enabled``). There is
no runtime/query/env force-pass bypass.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.domain.decision import DecisionOutcome
from app.transactions.store import TransactionFileStore

#: Transaction-relative path of the canonical decision record.
DECISION_RELATIVE_PATH = "decisions/decision.json"


class DecisionRecord(BaseModel):
    decision_id: str = Field(min_length=1)
    transaction_id: str = Field(min_length=1)
    outcome: DecisionOutcome
    decided_at: str
    decision_source: str
    decision_version: str
    evidence_refs: list[str] = Field(default_factory=list)


def build_decision(
    transaction_id: str, source: str = "test-only", version: str = "m5.8-dev"
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=uuid.uuid4().hex,
        transaction_id=transaction_id,
        outcome=DecisionOutcome.PASS,
        decided_at=datetime.datetime.now(datetime.UTC).isoformat(),
        decision_source=source,
        decision_version=version,
    )


def read_decision(store: TransactionFileStore, transaction_id: str) -> DecisionRecord | None:
    if not store.artifact_exists(transaction_id, DECISION_RELATIVE_PATH):
        return None
    try:
        raw: dict[str, Any] = store.read_json(transaction_id, DECISION_RELATIVE_PATH)
        return DecisionRecord.model_validate(raw)
    except Exception:
        return None


def has_canonical_pass(store: TransactionFileStore, transaction_id: str) -> bool:
    record = read_decision(store, transaction_id)
    return record is not None and record.outcome == DecisionOutcome.PASS


def write_decision(
    store: TransactionFileStore, transaction_id: str, record: DecisionRecord
) -> None:
    store.write_json(
        transaction_id,
        DECISION_RELATIVE_PATH,
        record.model_dump(mode="json"),
    )
