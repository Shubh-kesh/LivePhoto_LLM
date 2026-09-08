"""Consumer status service (M5.8 §16).

S2S status lookup resolved within the authenticated consumer scope. Cross-consumer or
unknown lookups
behave as not-found. The response exposes only safe operational fields and allowlisted reason codes.
"""

from __future__ import annotations

from typing import Any

from app.integrations.consumers import ConsumerProfile
from app.integrations.store import IntegrationIndexStore, external_key_hash
from app.transactions.store import TransactionFileStore, TransactionStatus

#: Product-level status vocabulary exposed to the consuming application.
STATUS_READY = "READY"
STATUS_RETRY_REQUIRED = "RETRY_REQUIRED"
STATUS_ATTEMPT_LIMIT_EXCEEDED = "ATTEMPT_LIMIT_EXCEEDED"
STATUS_COMPLETED = "COMPLETED"
STATUS_CALLBACK_FAILED = "CALLBACK_FAILED"
STATUS_IN_PROGRESS = "IN_PROGRESS"


def _map_status(status: str) -> str:
    if status == TransactionStatus.COMPLETED.value:
        return STATUS_COMPLETED
    if status == TransactionStatus.ATTEMPT_LIMIT_EXCEEDED.value:
        return STATUS_ATTEMPT_LIMIT_EXCEEDED
    if status == TransactionStatus.CALLBACK_FAILED.value:
        return STATUS_CALLBACK_FAILED
    if (
        status == TransactionStatus.PORTRAIT_READY.value
        or status == TransactionStatus.DECISION_READY.value
    ):
        return STATUS_READY
    if status == TransactionStatus.CAPTURE_READY.value:
        return STATUS_IN_PROGRESS
    return STATUS_RETRY_REQUIRED


def resolve_status(
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    profile: ConsumerProfile,
    external_transaction_id: str,
) -> dict[str, Any] | None:
    """Return a safe status payload for the given consumer's external transaction, or None."""
    key_hash = external_key_hash(profile.consumer_id, external_transaction_id)
    mapping = index_store.get_external(key_hash)
    if mapping is None:
        return None
    internal_tx_id = mapping["internal_transaction_id"]
    if not isinstance(internal_tx_id, str):
        return None

    metadata = tx_store.read_transaction_json(internal_tx_id)
    attempts = _read_attempts(tx_store, internal_tx_id)
    status = str(metadata.get("status", ""))
    return {
        "transaction_id": external_transaction_id,
        "source": str(metadata.get("source", profile.consumer_id)),
        "status": _map_status(status),
        "attempt_count": attempts.get("attempt_count", 0),
        "max_attempts": profile.max_attempts,
        "reason_codes": list(attempts.get("reason_codes", [])),
        "created_at": str(metadata.get("created_at", "")),
        "updated_at": str(metadata.get("updated_at", metadata.get("created_at", ""))),
    }


def _read_attempts(tx_store: TransactionFileStore, internal_tx_id: str) -> dict[str, Any]:
    if not tx_store.artifact_exists(internal_tx_id, "attempts.json"):
        return {"attempt_count": 0, "reason_codes": []}
    try:
        data = tx_store.read_json(internal_tx_id, "attempts.json")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"attempt_count": 0, "reason_codes": []}
