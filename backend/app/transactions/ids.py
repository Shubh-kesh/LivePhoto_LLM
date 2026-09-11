"""LivePhoto-generated internal transaction IDs (pre-M6 usability improvement).

Exact format::

    LP-YYYYMMDDTHHMMSSmmmZ-RANDOM     e.g. LP-20260910T104543123Z-A7F3C2

- UTC only (timezone-aware datetime; server local timezone is never used).
- Fixed width, so lexicographic ordering approximately equals chronological ordering.
- Filesystem-safe: only ``A-Z``, ``0-9``, ``-`` (no ``:`` ``/`` ``\\`` ``+`` or spaces).
- ``RANDOM`` is a cryptographically random uppercase hex suffix (``secrets``); never a counter,
  PID, weak RNG or date/time alone.

Security note: the timestamp/random ID is **not** an authorization token. It is not used for
authentication/authorization and its unpredictability is not relied upon for security.

External (bank/consumer-supplied) transaction IDs are **never** generated or rewritten here; they
are preserved verbatim by the integration flow and only ever stored as ``external_transaction_id``.

New internal IDs are created through :func:`create_transaction_with_generated_id`, which retries a
bounded number of times on the (astronomically unlikely) filesystem collision, so an existing
transaction directory is never overwritten. Legacy 32-hex IDs remain valid/readable because the
store's general ``TRANSACTION_ID_PATTERN`` accepts both shapes.
"""

from __future__ import annotations

import datetime
import re
import secrets
from collections.abc import Callable
from typing import Any

from app.transactions.store import (
    TransactionExistsError,
    TransactionFileStore,
    TransactionStorageError,
)

#: Pattern for LivePhoto-generated internal transaction IDs.
INTERNAL_TRANSACTION_ID_PATTERN = re.compile(r"^LP-\d{8}T\d{9}Z-[A-F0-9]{6,8}$")

PREFIX = "LP"
#: 3 bytes -> 6 uppercase hex characters (readable; the pattern also accepts 8).
DEFAULT_SUFFIX_BYTES = 3
DEFAULT_MAX_ATTEMPTS = 5


def generate_internal_transaction_id(
    now: datetime.datetime | None = None,
    *,
    suffix_bytes: int = DEFAULT_SUFFIX_BYTES,
) -> str:
    """Generate a new LivePhoto-internal transaction ID (UTC + random suffix).

    ``now`` must be timezone-aware; a non-UTC aware datetime is normalized to UTC. A naive datetime
    is rejected (never guess a timezone). The optional parameter makes the timestamp deterministic
    for tests.
    """
    moment = now if now is not None else datetime.datetime.now(datetime.UTC)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("generate_internal_transaction_id requires a timezone-aware datetime")
    moment = moment.astimezone(datetime.UTC)
    timestamp = moment.strftime("%Y%m%dT%H%M%S") + f"{moment.microsecond // 1000:03d}Z"
    suffix = secrets.token_hex(suffix_bytes).upper()
    return f"{PREFIX}-{timestamp}-{suffix}"


def create_transaction_with_generated_id(
    store: TransactionFileStore,
    metadata_factory: Callable[[str], dict[str, Any]],
    *,
    now: datetime.datetime | None = None,
    id_factory: Callable[[], str] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> str:
    """Generate an ID and atomically create the transaction, retrying on collision.

    The filesystem store remains authoritative: ``create_transaction`` uses an exclusive ``mkdir``,
    so a collision raises ``TransactionExistsError`` and we generate a fresh suffix (bounded
    retries). An existing transaction directory is never overwritten. ``id_factory`` is injectable
    for deterministic collision tests.
    """
    generate = id_factory or (lambda: generate_internal_transaction_id(now))
    last_error: TransactionExistsError | None = None
    for _ in range(max_attempts):
        candidate = generate()
        try:
            store.create_transaction(candidate, metadata_factory(candidate))
            return candidate
        except TransactionExistsError as exc:
            last_error = exc
            continue
    raise TransactionStorageError("could not allocate a unique transaction id") from last_error
