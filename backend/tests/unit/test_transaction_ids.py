"""LivePhoto-internal transaction ID generation tests (pre-M6).

Format: LP-YYYYMMDDTHHMMSSmmmZ-RANDOM (UTC + cryptographically random uppercase hex suffix).
"""

from __future__ import annotations

import datetime
import re

import pytest

from app.transactions import TransactionFileStore, TransactionStorageError
from app.transactions.ids import (
    INTERNAL_TRANSACTION_ID_PATTERN,
    create_transaction_with_generated_id,
    generate_internal_transaction_id,
)

UTC = datetime.UTC
#: Conceptual pattern from the requirement: ^LP-\d{8}T\d{9}Z-[A-F0-9]{6,8}$
FORMAT = re.compile(r"^LP-\d{8}T\d{9}Z-[A-F0-9]{6,8}$")


def _make_store(tmp_path) -> TransactionFileStore:
    store = TransactionFileStore(str(tmp_path / "storage"))
    store.initialize()
    return store


def test_generated_id_matches_format() -> None:
    tx_id = generate_internal_transaction_id()
    assert FORMAT.fullmatch(tx_id)
    assert INTERNAL_TRANSACTION_ID_PATTERN.fullmatch(tx_id)
    assert tx_id.startswith("LP-")


def test_supplied_datetime_produces_expected_utc_timestamp() -> None:
    moment = datetime.datetime(2026, 9, 10, 10, 45, 43, 123000, tzinfo=UTC)
    tx_id = generate_internal_transaction_id(now=moment)
    assert tx_id.startswith("LP-20260910T104543123Z-")


def test_non_utc_aware_datetime_is_normalized_to_utc() -> None:
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    # 16:15:43.123 +05:30 == 10:45:43.123 UTC on the same day.
    moment = datetime.datetime(2026, 9, 10, 16, 15, 43, 123000, tzinfo=tz)
    tx_id = generate_internal_transaction_id(now=moment)
    assert tx_id.startswith("LP-20260910T104543123Z-")


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        generate_internal_transaction_id(now=datetime.datetime(2026, 9, 10, 10, 45, 43))


def test_multiple_ids_at_same_timestamp_are_unique() -> None:
    moment = datetime.datetime(2026, 9, 10, 10, 45, 43, 123000, tzinfo=UTC)
    ids = {generate_internal_transaction_id(now=moment) for _ in range(500)}
    assert len(ids) == 500
    for tx_id in ids:
        assert tx_id.startswith("LP-20260910T104543123Z-")


def test_generated_id_is_filesystem_safe() -> None:
    tx_id = generate_internal_transaction_id()
    assert re.fullmatch(r"[A-Z0-9-]+", tx_id)
    for forbidden in ("/", "\\", ":", " ", "+"):
        assert forbidden not in tx_id


def test_lexicographic_ordering_matches_time() -> None:
    a = generate_internal_transaction_id(
        now=datetime.datetime(2026, 9, 10, 10, 45, 1, 1000, tzinfo=UTC)
    )
    b = generate_internal_transaction_id(
        now=datetime.datetime(2026, 9, 10, 10, 45, 2, 100000, tzinfo=UTC)
    )
    c = generate_internal_transaction_id(
        now=datetime.datetime(2026, 9, 11, 8, 10, 0, 0, tzinfo=UTC)
    )
    assert a < b < c


def test_collision_retries_and_never_overwrites(tmp_path) -> None:
    store = _make_store(tmp_path)
    existing = "LP-20260910T104543123Z-AAAAAA"
    store.create_transaction(existing, {"transaction_id": existing})
    sequence = iter([existing, "LP-20260910T104543123Z-BBBBBB"])
    tx_id = create_transaction_with_generated_id(
        store,
        lambda tid: {"transaction_id": tid},
        id_factory=lambda: next(sequence),
    )
    assert tx_id == "LP-20260910T104543123Z-BBBBBB"
    # The pre-existing transaction directory is untouched.
    assert store.transaction_exists(existing)
    assert store.read_transaction_json(existing)["transaction_id"] == existing


def test_collision_exhaustion_fails_closed_without_overwrite(tmp_path) -> None:
    store = _make_store(tmp_path)
    existing = "LP-20260910T104543123Z-AAAAAA"
    store.create_transaction(existing, {"transaction_id": existing})
    with pytest.raises(TransactionStorageError):
        create_transaction_with_generated_id(
            store,
            lambda tid: {"transaction_id": tid},
            id_factory=lambda: existing,
            max_attempts=3,
        )
    assert store.transaction_exists(existing)
    assert store.read_transaction_json(existing)["transaction_id"] == existing


def test_create_transaction_with_generated_id_uses_new_format(tmp_path) -> None:
    store = _make_store(tmp_path)
    tx_id = create_transaction_with_generated_id(
        store, lambda tid: {"transaction_id": tid, "status": "CREATED"}
    )
    assert FORMAT.fullmatch(tx_id)
    assert store.transaction_exists(tx_id)
    assert store.read_transaction_json(tx_id)["transaction_id"] == tx_id
