"""Test-only canonical decision writer (M5.8 §17).

Registered ONLY when ``app_env`` is local/test/development AND ``decision_test_writer_enabled``.
Never registered in UAT/production. This is the only M5.8 writer of a canonical ``PASS`` decision so
the Submit path is exercisable without a production decision engine. There is no force-pass
query/env/runtime bypass.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.api.deps import require_active_session, require_csrf
from app.transactions import TransactionStatus
from app.transactions.decisions import build_decision, write_decision

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/test-decision")
def test_decision(request: Request) -> Response:
    record = require_active_session(request)
    require_csrf(request, record)
    internal_tx_id = record["transaction_id"]
    store = request.app.state.transaction_store
    decision = build_decision(internal_tx_id, source="test-only", version="m5.8-dev")
    write_decision(store, internal_tx_id, decision)
    store.update_transaction_status(internal_tx_id, TransactionStatus.DECISION_READY.value)
    return JSONResponse(
        {
            "decision_id": decision.decision_id,
            "outcome": decision.outcome.value,
            "submission_ready": True,
        }
    )
