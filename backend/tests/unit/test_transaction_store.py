"""TransactionFileStore tests (M5.7 §84). Uses temp directories; no real storage."""

from __future__ import annotations

import pytest

from app.transactions import (
    ArtifactNotFoundError,
    ArtifactType,
    TransactionExistsError,
    TransactionFileStore,
    TransactionPathError,
    is_valid_transaction_id,
)


@pytest.fixture
def store(tmp_path):
    instance = TransactionFileStore(str(tmp_path / "storage"))
    instance.initialize()
    return instance


def test_valid_transaction_id_format() -> None:
    assert is_valid_transaction_id("a" * 32)
    assert not is_valid_transaction_id("../../etc/passwd")
    assert not is_valid_transaction_id("abc")
    assert not is_valid_transaction_id("not a path")


def test_create_transaction_and_folder_first(store: TransactionFileStore) -> None:
    tx_id = "b" * 32
    store.create_transaction(tx_id, {"transaction_id": tx_id, "status": "CREATED"})
    assert store.transaction_exists(tx_id)
    metadata = store.read_transaction_json(tx_id)
    assert metadata["status"] == "CREATED"


def test_duplicate_transaction_rejected(store: TransactionFileStore) -> None:
    tx_id = "c" * 32
    store.create_transaction(tx_id, {})
    with pytest.raises(TransactionExistsError):
        store.create_transaction(tx_id, {})


def test_nested_artifact_write_and_read(store: TransactionFileStore) -> None:
    tx_id = "d" * 32
    store.create_transaction(tx_id, {})
    ref = store.write_artifact(
        tx_id, ArtifactType.SELECTED_ORIGINAL_CAPTURE, b"jpeg-bytes", content_type="image/jpeg"
    )
    assert ref.relative_path == "capture/selected-original.jpg"
    assert len(ref.sha256) == 64
    import hashlib

    assert ref.sha256 == hashlib.sha256(b"jpeg-bytes").hexdigest()
    data = store.read_artifact(tx_id, ref.relative_path)
    assert data == b"jpeg-bytes"


def test_atomic_json_write(store: TransactionFileStore) -> None:
    tx_id = "e" * 32
    store.create_transaction(tx_id, {})
    store.write_json(tx_id, "vlm/result.json", {"classification": "LIVE"})
    parsed = store.read_json(tx_id, "vlm/result.json")
    assert parsed["classification"] == "LIVE"
    # No temp files left behind.
    tx_dir = store.transaction_dir(tx_id)
    leftovers = [p for p in tx_dir.rglob("*") if p.name.startswith(".tmp-")]
    assert leftovers == []


def test_missing_transaction_artifact(store: TransactionFileStore) -> None:
    tx_id = "f" * 32
    store.create_transaction(tx_id, {})
    with pytest.raises(ArtifactNotFoundError):
        store.read_artifact(tx_id, "capture/missing.jpg")
    with pytest.raises(ArtifactNotFoundError):
        store.read_artifact("g" * 32, "capture/selected-original.jpg")


def test_traversal_rejected(store: TransactionFileStore) -> None:
    tx_id = "h" * 32
    store.create_transaction(tx_id, {})
    with pytest.raises(TransactionPathError):
        store.resolve_artifact(tx_id, "../../../etc/passwd")
    with pytest.raises(TransactionPathError):
        store.resolve_artifact(tx_id, "capture/../../secret")
    with pytest.raises(TransactionPathError):
        store.resolve_artifact("../../x" * 16, "capture/a.jpg")


def test_absolute_path_rejected(store: TransactionFileStore) -> None:
    tx_id = "i" * 32
    with pytest.raises(TransactionPathError):
        store.resolve_artifact(tx_id, "/etc/passwd")


def test_symlink_escape_rejected(store: TransactionFileStore, tmp_path) -> None:
    outside = tmp_path / "outside-secret"
    outside.write_text("secret")
    tx_id = "j" * 32
    store.create_transaction(tx_id, {})
    tx_dir = store.transaction_dir(tx_id)
    (tx_dir / "link.jpg").symlink_to(outside)
    with pytest.raises(TransactionPathError):
        store.resolve_artifact(tx_id, "link.jpg")


def test_missing_transaction_dir(store: TransactionFileStore) -> None:
    assert store.transaction_exists("k" * 32) is False


def test_transaction_status_update(store: TransactionFileStore) -> None:
    tx_id = "l" * 32
    store.create_transaction(tx_id, {"status": "CREATED"})
    store.update_transaction_status(tx_id, "CAPTURE_READY")
    assert store.read_transaction_json(tx_id)["status"] == "CAPTURE_READY"


def test_health_check(store: TransactionFileStore) -> None:
    health = store.check_health()
    assert health.ok is True
    # Probe file must be cleaned up.
    probes = list(store.root.rglob(".livephoto-probe"))
    assert probes == []
