"""Launch-session service (M5.8 §3, §7, §8).

Creates a LivePhoto-internal transaction BEFORE any capture, mints an opaque launch
capability token (>=256-bit,
hash-only persistence) and returns a short browser launch URL. Reissue preserves the same internal
transaction and revokes previous active launch tokens.
"""

from __future__ import annotations

import datetime
import re
import secrets
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.integrations.consumers import ConsumerProfile
from app.integrations.store import IntegrationIndexStore, external_key_hash, sha256_hex
from app.transactions.store import (
    TransactionExistsError,
    TransactionFileStore,
    TransactionStatus,
)

#: External correlation IDs are bounded and free of path characters; they are never used as paths.
EXTERNAL_TRANSACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class LaunchSessionRequest(BaseModel):
    """Strict S2S launch request. ``extra="forbid"`` rejects legacy token/hash/unknown fields."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    ocr_required: bool = False
    camera_config: str = "1"
    white_background: bool = True
    output_file_format: str = "jpeg"
    watermark: str = ""


@dataclass(frozen=True)
class LaunchResult:
    internal_transaction_id: str
    external_transaction_id: str
    launch_session_id: str
    launch_url: str
    expires_at: str
    expires_in_seconds: int


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _is_valid_external_id(value: str) -> bool:
    return bool(EXTERNAL_TRANSACTION_ID_PATTERN.fullmatch(value))


def _public_base_url(settings: Settings) -> str:
    if not settings.public_livephoto_base_url:
        raise ValueError("PUBLIC_LIVEPHOTO_BASE_URL is not configured")
    return settings.public_livephoto_base_url.rstrip("/")


def _build_launch_token_and_url(settings: Settings, internal_tx_id: str) -> tuple[str, str, str]:
    """Generate a >=256-bit opaque launch token; return (raw_token, token_hash, launch_url).

    Only the SHA-256 hash is ever persisted. The raw token appears only in the returned launch URL.
    """
    raw_token = secrets.token_urlsafe(32)  # 256 bits of entropy
    token_hash = sha256_hex(raw_token.encode("utf-8"))
    base = _public_base_url(settings)
    launch_url = f"{base}/xbiz/live_photo/l/{raw_token}"
    return raw_token, token_hash, launch_url


def _transaction_metadata(
    settings: Settings,
    internal_tx_id: str,
    profile: ConsumerProfile,
    req: LaunchSessionRequest,
    status: str,
) -> dict[str, object]:
    return {
        "transaction_id": internal_tx_id,
        "external_transaction_id": req.transaction_id,
        "consumer_id": profile.consumer_id,
        "source": req.source,
        "ocr_required": req.ocr_required,
        "camera_config": req.camera_config,
        "white_background": req.white_background,
        "output_file_format": req.output_file_format,
        "status": status,
        "created_at": _utc_now().isoformat(),
        "app_version": settings.app_version,
    }


def create_launch(
    settings: Settings,
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    profile: ConsumerProfile,
    req: LaunchSessionRequest,
) -> LaunchResult:
    """Create a new transaction + launch session (M5.8 §3, §7)."""
    if not _is_valid_external_id(req.transaction_id):
        from app.transactions.store import TransactionPathError

        raise TransactionPathError("invalid external transaction id")

    key_hash = external_key_hash(profile.consumer_id, req.transaction_id)
    with index_store.lock_external(key_hash):
        if index_store.get_external(key_hash) is not None:
            raise TransactionExistsError("transaction already exists for this consumer")

        internal_tx_id = uuid.uuid4().hex
        tx_store.create_transaction(
            internal_tx_id,
            _transaction_metadata(
                settings, internal_tx_id, profile, req, TransactionStatus.LAUNCHED.value
            ),
        )
        index_store.put_external(
            key_hash,
            {
                "internal_transaction_id": internal_tx_id,
                "external_transaction_id": req.transaction_id,
                "consumer_id": profile.consumer_id,
                "created_at": _utc_now().isoformat(),
            },
        )

    raw_token, token_hash, launch_url = _build_launch_token_and_url(settings, internal_tx_id)
    return _store_launch_token(
        settings,
        tx_store,
        index_store,
        internal_tx_id,
        req.transaction_id,
        raw_token,
        token_hash,
        launch_url,
    )


def reissue_launch(
    settings: Settings,
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    profile: ConsumerProfile,
    external_transaction_id: str,
) -> LaunchResult:
    """Reissue a launch for an existing transaction: same internal tx, revoke old tokens."""
    if not _is_valid_external_id(external_transaction_id):
        from app.transactions.store import TransactionPathError

        raise TransactionPathError("invalid external transaction id")

    key_hash = external_key_hash(profile.consumer_id, external_transaction_id)
    mapping = index_store.get_external(key_hash)
    if mapping is None:
        from app.transactions.store import ArtifactNotFoundError

        raise ArtifactNotFoundError("transaction not found")
    internal_tx_id = mapping["internal_transaction_id"]

    with tx_store.lock_transaction(internal_tx_id):
        _revoke_active_launch_tokens(tx_store, index_store, internal_tx_id)
        raw_token, token_hash, launch_url = _build_launch_token_and_url(settings, internal_tx_id)
        return _store_launch_token(
            settings,
            tx_store,
            index_store,
            internal_tx_id,
            external_transaction_id,
            raw_token,
            token_hash,
            launch_url,
        )


def _store_launch_token(
    settings: Settings,
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    internal_tx_id: str,
    external_transaction_id: str,
    raw_token: str,
    token_hash: str,
    launch_url: str,
) -> LaunchResult:
    ttl = settings.launch_token_ttl_seconds
    now = _utc_now()
    expires = now + datetime.timedelta(seconds=ttl)
    index_store.put_launch_token(
        token_hash,
        {
            "transaction_id": internal_tx_id,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        },
    )
    launch_session_id = uuid.uuid4().hex
    active = _read_active_launches(tx_store, internal_tx_id)
    active.append(
        {
            "launch_session_id": launch_session_id,
            "token_hash": token_hash,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
    )
    tx_store.write_json(internal_tx_id, "launch/active-launches.json", {"active": active})
    return LaunchResult(
        internal_transaction_id=internal_tx_id,
        external_transaction_id=external_transaction_id,
        launch_session_id=launch_session_id,
        launch_url=launch_url,
        expires_at=expires.isoformat(),
        expires_in_seconds=ttl,
    )


def _read_active_launches(
    tx_store: TransactionFileStore, internal_tx_id: str
) -> list[dict[str, object]]:
    if not tx_store.artifact_exists(internal_tx_id, "launch/active-launches.json"):
        return []
    try:
        data = tx_store.read_json(internal_tx_id, "launch/active-launches.json")
        active = data.get("active", [])
        return active if isinstance(active, list) else []
    except Exception:
        return []


def _revoke_active_launch_tokens(
    tx_store: TransactionFileStore,
    index_store: IntegrationIndexStore,
    internal_tx_id: str,
) -> None:
    for entry in _read_active_launches(tx_store, internal_tx_id):
        token_hash = entry.get("token_hash")
        if isinstance(token_hash, str):
            index_store.delete_launch_token(token_hash)
    tx_store.write_json(internal_tx_id, "launch/active-launches.json", {"active": []})
