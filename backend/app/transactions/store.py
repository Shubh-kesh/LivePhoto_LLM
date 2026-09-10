"""Transaction-scoped filesystem file store (M5.7 §1-13, §83).

Filesystem-only by design: no GCS/S3/Azure/generic object-storage abstraction. LivePhoto sees the
storage location as a plain filesystem path (``FILE_STORAGE_ROOT``); UAT/production mount an
enterprise file-storage volume there.

Every persisted artifact for a transaction lives under:

    <FILE_STORAGE_ROOT>/transactions/<transaction_id>/

Security invariants:
- Transaction IDs are validated (opaque, filesystem-safe) before any path is built.
- Every resolved path is confined below the storage root; ``..``/absolute/encoded traversal and
  symlink escapes are rejected.
- JSON metadata writes are atomic (temp file + fsync + atomic rename).
- Conservative file permissions (never world-writable 0777).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.transactions.artifacts import ARTIFACT_RELATIVE_PATHS, ArtifactReference, ArtifactType

#: Opaque, filesystem-safe, globally unique transaction IDs (not PII-derived). No dots/slashes.
TRANSACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

MAX_ARTIFACT_BYTES = 50 * 1024 * 1024


class TransactionStatus(StrEnum):
    """Transaction lifecycle states (M5.8 §14).

    Superset of the M5.7 free-form status strings so previously persisted values remain valid.
    """

    LAUNCHED = "LAUNCHED"
    CREATED = "CREATED"  # legacy experiment flow
    CAPTURE_READY = "CAPTURE_READY"
    VLM_EVALUATED = "VLM_EVALUATED"
    PORTRAIT_PROCESSING = "PORTRAIT_PROCESSING"
    PORTRAIT_READY = "PORTRAIT_READY"
    DECISION_READY = "DECISION_READY"
    SUBMITTED = "SUBMITTED"
    COMPLETED = "COMPLETED"
    CALLBACK_FAILED = "CALLBACK_FAILED"
    ATTEMPT_LIMIT_EXCEEDED = "ATTEMPT_LIMIT_EXCEEDED"
    FAILED = "FAILED"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"

    @classmethod
    def from_value(cls, value: str) -> TransactionStatus:
        try:
            return cls(value)
        except ValueError:
            return cls.TECHNICAL_ERROR


#: Terminal states: capture/attempts cannot restart and no further submission proceeds.
TERMINAL_TRANSACTION_STATUSES: frozenset[TransactionStatus] = frozenset(
    {
        TransactionStatus.COMPLETED,
        TransactionStatus.ATTEMPT_LIMIT_EXCEEDED,
        TransactionStatus.FAILED,
    }
)


class TransactionStorageError(Exception):
    """Typed technical storage failure (M5.7 §10, §77)."""


def _utc_now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()


class TransactionNotFoundError(TransactionStorageError):
    pass


class TransactionExistsError(TransactionStorageError):
    pass


class ArtifactNotFoundError(TransactionStorageError):
    pass


class TransactionPathError(TransactionStorageError):
    pass


@dataclass(frozen=True)
class StorageHealth:
    ok: bool
    detail: str


def is_valid_transaction_id(transaction_id: str) -> bool:
    return bool(TRANSACTION_ID_PATTERN.fullmatch(transaction_id))


class TransactionFileStore:
    """Filesystem transaction store. Explicitly NOT a cloud-storage abstraction."""

    def __init__(self, root: str, transactions_dir: str = "transactions") -> None:
        self._root = Path(root)
        self._transactions_root = self._root / transactions_dir

    @property
    def root(self) -> Path:
        return self._root

    def initialize(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._transactions_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TransactionStorageError(f"cannot create storage root: {exc}") from exc

    # ------------------------------------------------------------------ paths

    def _validate_transaction_id(self, transaction_id: str) -> None:
        if not is_valid_transaction_id(transaction_id):
            raise TransactionPathError("invalid transaction id")

    def _confine(self, *parts: str) -> Path:
        """Build a path below the transactions root, resolving traversal/symlink escapes."""
        try:
            base = self._transactions_root.resolve()
            candidate = base.joinpath(*parts)
            resolved = candidate.resolve()
        except OSError as exc:
            raise TransactionPathError(f"path resolution failed: {exc}") from exc
        if not resolved.is_relative_to(base):
            raise TransactionPathError("path escapes the storage root")
        return resolved

    def transaction_dir(self, transaction_id: str) -> Path:
        self._validate_transaction_id(transaction_id)
        return self._confine(transaction_id)

    def resolve_artifact(self, transaction_id: str, relative_path: str) -> Path:
        """Resolve a transaction-relative artifact path (M5.7 §14)."""
        self._validate_transaction_id(transaction_id)
        if not relative_path or relative_path.startswith("/") or "\\" in relative_path:
            raise TransactionPathError("invalid artifact relative path")
        parts = [part for part in relative_path.split("/") if part and part not in (".", "..")]
        if parts != relative_path.split("/"):
            raise TransactionPathError("artifact path must be transaction-relative")
        return self._confine(transaction_id, *parts)

    # ------------------------------------------------------------------ lifecycle

    def create_transaction(self, transaction_id: str, metadata: dict[str, Any]) -> None:
        """Create the transaction folder FIRST (M5.7 §2, §10)."""
        self._validate_transaction_id(transaction_id)
        try:
            self._transactions_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TransactionStorageError(f"cannot create storage root: {exc}") from exc
        tx_dir = self._confine(transaction_id)
        try:
            tx_dir.mkdir(parents=False)
        except FileExistsError as exc:
            raise TransactionExistsError(f"transaction already exists: {transaction_id}") from exc
        except OSError as exc:
            raise TransactionStorageError(f"cannot create transaction folder: {exc}") from exc
        try:
            self.write_json(transaction_id, "transaction.json", metadata)
        except TransactionStorageError:
            # Do not leave a half-created transaction folder behind.
            tx_dir.rmdir()
            raise

    def transaction_exists(self, transaction_id: str) -> bool:
        return self.transaction_dir(transaction_id).is_dir()

    @contextmanager
    def lock_transaction(self, transaction_id: str) -> Iterator[None]:
        """Hold an exclusive advisory lock on a transaction for a read-modify-write block.

        M5.8 shared-filesystem concurrency: status transitions, attempt counting, launch-token
        revocation and browser-session rotation must be serialized per transaction across workers.
        """
        import fcntl

        self._validate_transaction_id(transaction_id)
        tx_dir = self._confine(transaction_id)
        tx_dir.mkdir(parents=True, exist_ok=True)
        lock_path = tx_dir / ".lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def read_transaction_json(self, transaction_id: str) -> dict[str, Any]:
        return self.read_json(transaction_id, "transaction.json")

    def update_transaction_status(self, transaction_id: str, status: str) -> None:
        metadata = self.read_transaction_json(transaction_id)
        current = TransactionStatus.from_value(str(metadata.get("status", "")))
        new_status = TransactionStatus.from_value(status)
        # Terminal states are sticky: never regress from COMPLETED / ATTEMPT_LIMIT_EXCEEDED /
        # FAILED.
        if (
            current in TERMINAL_TRANSACTION_STATUSES
            and new_status not in TERMINAL_TRANSACTION_STATUSES
        ):
            return
        metadata["status"] = status
        metadata["updated_at"] = _utc_now_iso()
        self.write_json(transaction_id, "transaction.json", metadata)

    # ------------------------------------------------------------------ artifacts

    def write_artifact(
        self,
        transaction_id: str,
        artifact_type: ArtifactType,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> ArtifactReference:
        """Write an artifact under the transaction folder and return its reference."""
        if len(data) > MAX_ARTIFACT_BYTES:
            raise TransactionStorageError("artifact exceeds the size limit")
        relative_path = ARTIFACT_RELATIVE_PATHS[artifact_type]
        target = self.resolve_artifact(transaction_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(target, data)
        return ArtifactReference(
            transaction_id=transaction_id,
            artifact_type=artifact_type,
            relative_path=relative_path,
            content_type=content_type,
            size_bytes=len(data),
            sha256=sha256_hex(data),
        )

    def read_artifact(self, transaction_id: str, relative_path: str) -> bytes:
        path = self.resolve_artifact(transaction_id, relative_path)
        if not path.is_file():
            raise ArtifactNotFoundError(f"artifact not found: {relative_path}")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise TransactionStorageError(f"cannot read artifact: {exc}") from exc

    def write_bytes(self, transaction_id: str, relative_path: str, data: bytes) -> None:
        """Atomically write bytes at a transaction-relative path (root-confined).

        Used for staging artifacts (e.g. portrait candidates) before they are promoted to a
        canonical artifact path.
        """
        if len(data) > MAX_ARTIFACT_BYTES:
            raise TransactionStorageError("artifact exceeds the size limit")
        target = self.resolve_artifact(transaction_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(target, data)

    def artifact_exists(self, transaction_id: str, relative_path: str) -> bool:
        return self.resolve_artifact(transaction_id, relative_path).is_file()

    def remove_artifact(self, transaction_id: str, relative_path: str) -> None:
        """Best-effort removal of a transaction-relative artifact (root-confined)."""
        target = self.resolve_artifact(transaction_id, relative_path)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise TransactionStorageError(f"cannot remove artifact: {exc}") from exc

    # ------------------------------------------------------------------ JSON

    def write_json(self, transaction_id: str, relative_path: str, obj: dict[str, Any]) -> None:
        payload = json.dumps(obj, sort_keys=True).encode("utf-8")
        target = self.resolve_artifact(transaction_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(target, payload)

    def read_json(self, transaction_id: str, relative_path: str) -> dict[str, Any]:
        raw = self.read_artifact(transaction_id, relative_path)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransactionStorageError(f"corrupt JSON metadata: {exc}") from exc
        if not isinstance(parsed, dict):
            raise TransactionStorageError("metadata must be a JSON object")
        return parsed

    # ------------------------------------------------------------------ atomic

    def _write_atomic(self, target: Path, data: bytes) -> None:
        import tempfile

        directory = target.parent
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=directory)
            os.close(fd)
            tmp = Path(tmp_name)
            tmp.write_bytes(data)
            with tmp.open("rb") as handle:
                os.fsync(handle.fileno())
            # Conservative permissions: application-only (M5.7 §75).
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        except OSError as exc:
            raise TransactionStorageError(f"atomic write failed: {exc}") from exc

    # ------------------------------------------------------------------ health

    def check_health(self) -> StorageHealth:
        """Readiness: root exists/creatable and writable, without writing customer artifacts.

        A temporary probe file is created and removed (M5.7 §78).
        """
        try:
            self.initialize()
            probe = self._transactions_root / ".livephoto-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return StorageHealth(ok=False, detail=f"storage not writable: {exc}")
        return StorageHealth(ok=True, detail="filesystem storage ready")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
