"""Portrait processor tests (M5.7 §85). Uses a deterministic fake segmentation matte."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.config import Settings
from app.portrait import (
    FakePortraitSegmentation,
    PortraitProcessingError,
    PortraitProcessor,
)
from app.portrait.crop import CROP_VERSION
from app.transactions import (
    ArtifactReference,
    ArtifactType,
    TransactionFileStore,
)


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "app_env": "test",
        "portrait_processing_enabled": True,
        "portrait_background_mode": "solid",
        "portrait_background_color": "#FFFFFF",
        "portrait_crop_mode": "passport",
        "portrait_output_format": "jpeg",
        "portrait_jpeg_quality": 95,
        "portrait_model_path": "",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


def _jpeg(width: int = 480, height: int = 640) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (120, 140, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _source(tx_id: str) -> ArtifactReference:
    return ArtifactReference(
        transaction_id=tx_id,
        artifact_type=ArtifactType.SELECTED_ORIGINAL_CAPTURE,
        relative_path="capture/selected-original.jpg",
        content_type="image/jpeg",
    )


@pytest.fixture
def store(tmp_path) -> TransactionFileStore:
    instance = TransactionFileStore(str(tmp_path / "storage"))
    instance.initialize()
    return instance


def _prepare(store: TransactionFileStore) -> tuple[PortraitProcessor, str]:
    tx_id = "p" * 32
    store.create_transaction(tx_id, {"status": "CREATED"})
    store.write_artifact(tx_id, ArtifactType.SELECTED_ORIGINAL_CAPTURE, _jpeg())
    processor = PortraitProcessor(
        _settings(),
        store,
        segmentation=FakePortraitSegmentation(),
    )
    return processor, tx_id


@pytest.mark.asyncio
async def test_successful_processing_contract(store: TransactionFileStore) -> None:
    processor, tx_id = _prepare(store)
    result = await processor.process(_source(tx_id), tx_id)
    assert result.status == "SUCCESS"
    assert result.output_artifact.relative_path == "portrait/processed.jpg"
    assert result.crop_version == CROP_VERSION
    assert result.background_color == "#FFFFFF"
    assert result.width > 0 and result.height > 0
    # 3:4 aspect ratio.
    assert abs(result.width / result.height - 3 / 4) < 0.02
    # Output file exists and is a JPEG.
    assert store.artifact_exists(tx_id, "portrait/processed.jpg")
    meta = store.read_json(tx_id, "portrait/processing.json")
    assert meta["status"] == "SUCCESS"
    assert meta["source_artifact"] == "capture/selected-original.jpg"
    assert store.read_transaction_json(tx_id)["status"] == "PORTRAIT_READY"


@pytest.mark.asyncio
async def test_original_is_never_overwritten(store: TransactionFileStore) -> None:
    processor, tx_id = _prepare(store)
    original = store.read_artifact(tx_id, "capture/selected-original.jpg")
    await processor.process(_source(tx_id), tx_id)
    assert store.read_artifact(tx_id, "capture/selected-original.jpg") == original


@pytest.mark.asyncio
async def test_idempotent_output_path(store: TransactionFileStore) -> None:
    processor, tx_id = _prepare(store)
    first = await processor.process(_source(tx_id), tx_id)
    second = await processor.process(_source(tx_id), tx_id)
    assert first.output_artifact.relative_path == second.output_artifact.relative_path
    assert first.output_artifact.relative_path == "portrait/processed.jpg"


def test_background_color_validation() -> None:
    with pytest.raises(ValueError):
        _settings(portrait_background_color="white")
    parsed = _settings(portrait_background_color="#aabbcc")
    assert parsed.portrait_background_color == "#AABBCC"


def test_disabled_processing(store: TransactionFileStore) -> None:
    tx_id = "q" * 32
    store.create_transaction(tx_id, {})
    store.write_artifact(tx_id, ArtifactType.SELECTED_ORIGINAL_CAPTURE, _jpeg())
    processor = PortraitProcessor(
        _settings(portrait_processing_enabled=False),
        store,
        segmentation=FakePortraitSegmentation(),
    )
    with pytest.raises(PortraitProcessingError):
        # sync path for config check
        import asyncio

        asyncio.run(processor.process(_source(tx_id), tx_id))


@pytest.mark.asyncio
async def test_invalid_source(store: TransactionFileStore) -> None:
    tx_id = "r" * 32
    store.create_transaction(tx_id, {})
    store.write_artifact(tx_id, ArtifactType.SELECTED_ORIGINAL_CAPTURE, b"not an image")
    processor = PortraitProcessor(
        _settings(),
        store,
        segmentation=FakePortraitSegmentation(),
    )
    with pytest.raises(PortraitProcessingError):
        await processor.process(_source(tx_id), tx_id)
    assert store.read_transaction_json(tx_id)["status"] == "TECHNICAL_ERROR"


@pytest.mark.asyncio
async def test_model_failure_is_typed_error(store: TransactionFileStore) -> None:
    _processor, tx_id = _prepare(store)
    failing = PortraitProcessor(
        _settings(),
        store,
        segmentation=FakePortraitSegmentation(fail=True),
    )
    with pytest.raises(PortraitProcessingError):
        await failing.process(_source(tx_id), tx_id)
    assert store.read_transaction_json(tx_id)["status"] == "TECHNICAL_ERROR"


def test_json_metadata_contains_no_image_data(store: TransactionFileStore) -> None:
    processor, tx_id = _prepare(store)
    import asyncio

    asyncio.run(processor.process(_source(tx_id), tx_id))
    raw = store.read_artifact(tx_id, "portrait/processing.json")
    text = raw.decode("utf-8")
    assert "base64" not in text.lower()
    assert "sha256" in text or "model_hash" in text
