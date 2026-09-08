"""Shared-filesystem index store for M5.8 integration state.

Launch tokens, browser sessions and external-transaction lookups are authoritative on the shared
filesystem (never process memory). All files are write-once JSON written atomically (temp file +
fsync + atomic rename) and deleted on revocation. Root confinement and symlink-escape rejection are
preserved exactly as in ``TransactionFileStore``.

Layout under ``FILE_STORAGE_ROOT``:

    index/launch-tokens/<sha256(token)>.json      {transaction_id, created_at, expires_at}
    index/browser-sessions/<sha256(token)>.json   {transaction_id, csrf_hash, expires_at, revoked}
    index/external/<sha256(consumer:external)>.json {internal, external_transaction_id}
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class IntegrationIndexError(Exception):
    """Typed storage failure for integration indexes."""


class IntegrationIndexPathError(IntegrationIndexError):
    pass


class IntegrationIndexStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._index_root = self._root / "index"

    @property
    def root(self) -> Path:
        return self._root

    def initialize(self) -> None:
        try:
            (self._index_root / "launch-tokens").mkdir(parents=True, exist_ok=True)
            (self._index_root / "browser-sessions").mkdir(parents=True, exist_ok=True)
            (self._index_root / "external").mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise IntegrationIndexError(f"cannot create index root: {exc}") from exc

    def _confine(self, *parts: str) -> Path:
        try:
            base = self._index_root.resolve()
            candidate = base.joinpath(*parts)
            resolved = candidate.resolve()
        except OSError as exc:
            raise IntegrationIndexPathError(f"path resolution failed: {exc}") from exc
        if not resolved.is_relative_to(base):
            raise IntegrationIndexPathError("path escapes the index root")
        return resolved

    def _write_atomic(self, target: Path, obj: dict[str, Any]) -> None:
        import tempfile

        payload = json.dumps(obj, sort_keys=True).encode("utf-8")
        directory = target.parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=directory)
            os.close(fd)
            tmp = Path(tmp_name)
            tmp.write_bytes(payload)
            with tmp.open("rb") as handle:
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        except OSError as exc:
            raise IntegrationIndexError(f"atomic write failed: {exc}") from exc

    def _read(self, target: Path) -> dict[str, Any] | None:
        if not target.is_file():
            return None
        try:
            raw = json.loads(target.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrationIndexError(f"corrupt index entry: {exc}") from exc
        if not isinstance(raw, dict):
            raise IntegrationIndexError("index entry must be a JSON object")
        return raw

    # ------------------------------------------------------------- launch tokens
    def put_launch_token(self, token_hash: str, payload: dict[str, Any]) -> None:
        self._write_atomic(self._confine("launch-tokens", f"{token_hash}.json"), payload)

    def get_launch_token(self, token_hash: str) -> dict[str, Any] | None:
        return self._read(self._confine("launch-tokens", f"{token_hash}.json"))

    def delete_launch_token(self, token_hash: str) -> None:
        target = self._confine("launch-tokens", f"{token_hash}.json")
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise IntegrationIndexError(f"cannot delete launch token index: {exc}") from exc

    # ----------------------------------------------------------- browser sessions
    def put_browser_session(self, session_hash: str, payload: dict[str, Any]) -> None:
        self._write_atomic(self._confine("browser-sessions", f"{session_hash}.json"), payload)

    def get_browser_session(self, session_hash: str) -> dict[str, Any] | None:
        return self._read(self._confine("browser-sessions", f"{session_hash}.json"))

    def delete_browser_session(self, session_hash: str) -> None:
        target = self._confine("browser-sessions", f"{session_hash}.json")
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise IntegrationIndexError(f"cannot delete browser session index: {exc}") from exc

    # ---------------------------------------------------------- external mapping
    def put_external(self, key_hash: str, payload: dict[str, Any]) -> None:
        self._write_atomic(self._confine("external", f"{key_hash}.json"), payload)

    def get_external(self, key_hash: str) -> dict[str, Any] | None:
        return self._read(self._confine("external", f"{key_hash}.json"))

    @contextmanager
    def lock_external(self, key_hash: str) -> Iterator[None]:
        """Serialize the external-id claim/create to prevent duplicate internal transactions."""
        import fcntl

        lock_target = self._confine("external", f"{key_hash}.lock")
        lock_target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_target, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def external_key_hash(consumer_id: str, external_transaction_id: str) -> str:
    """Deterministic, filesystem-safe hash key for an external transaction lookup.

    The external ID never appears in a filename; only its SHA-256 over ``consumer:id`` is used.
    """
    return sha256_hex(f"{consumer_id}:{external_transaction_id}".encode())
