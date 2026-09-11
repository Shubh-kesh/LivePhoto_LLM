"""Portrait processor tests (M5.7 §85). Uses a deterministic fake segmentation matte."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from app.core.config import Settings
from app.portrait import (
    FakePortraitSegmentation,
    PortraitErrorCode,
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


class _WideMobileSegmentation:
    """Segmentation reproducing the mobile 720x1280 wide-shoulders geometry."""

    @property
    def info(self) -> dict[str, str]:
        return {"name": "wide-mobile-test", "backend": "test", "sha256": "fake"}

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        width, height = image.size
        yy, xx = np.mgrid[0:height, 0:width]
        head = ((xx - width / 2) / (width * 0.18)) ** 2 + (
            (yy - height * 0.28) / (height * 0.125)
        ) ** 2 <= 1.0
        half_width = np.maximum(width * 0.44 - 0.02 * (yy - height * 0.37), width * 0.16)
        shoulders = (
            (yy >= height * 0.37) & (yy <= height * 0.70) & (np.abs(xx - width / 2) <= half_width)
        )
        return (head | shoulders).astype(np.float32)


class _MismatchedAlphaSegmentation:
    """Deliberately returns an alpha whose shape does not match the source image."""

    @property
    def info(self) -> dict[str, str]:
        return {"name": "mismatch-test", "backend": "test", "sha256": "fake"}

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        return _WideMobileSegmentation().predict_alpha(image)[::2, ::2]


@pytest.mark.asyncio
async def test_mobile_720x1280_no_broadcasting_error(store: TransactionFileStore) -> None:
    """The confirmed failing source (720x1280, wide shoulders) must process without a broadcasting
    ValueError and produce a valid 3:4 portrait."""
    tx_id = "m" * 32
    store.create_transaction(tx_id, {"status": "CREATED"})
    store.write_artifact(tx_id, ArtifactType.SELECTED_ORIGINAL_CAPTURE, _jpeg(720, 1280))
    processor = PortraitProcessor(_settings(), store, segmentation=_WideMobileSegmentation())
    result = await processor.process(_source(tx_id), tx_id)
    assert result.status == "SUCCESS"
    assert result.width > 0 and result.height > 0
    assert abs(result.width / result.height - 3 / 4) < 0.02
    assert store.artifact_exists(tx_id, "portrait/processed.jpg")


@pytest.mark.asyncio
async def test_processor_rejects_crop_dimension_mismatch(store: TransactionFileStore) -> None:
    """The defensive foreground/alpha dimension check must raise a typed error (no silent wrong
    composite) when the alpha and image crop regions cannot match."""
    tx_id = "q" * 32
    store.create_transaction(tx_id, {"status": "CREATED"})
    store.write_artifact(tx_id, ArtifactType.SELECTED_ORIGINAL_CAPTURE, _jpeg(640, 800))
    processor = PortraitProcessor(_settings(), store, segmentation=_MismatchedAlphaSegmentation())
    with pytest.raises(PortraitProcessingError) as exc_info:
        await processor.process(_source(tx_id), tx_id)
    assert exc_info.value.code == PortraitErrorCode.PORTRAIT_INVALID_SOURCE


class _CorruptedFaceSegmentation:
    """Reproduces the confirmed failure geometry: primary face/head left side missing.

    Raw alpha is already fragmented (left side of the face absent) so the structural integrity gate
    must fail closed (retryable quality failure), never promoting a corrupted portrait.
    """

    @property
    def info(self) -> dict[str, str]:
        return {"name": "corrupted-face-test", "backend": "test", "sha256": "fake"}

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        width, height = image.size
        alpha = np.zeros((height, width), dtype=np.float32)
        yy, xx = np.mgrid[0:height, 0:width]
        cx = 0.5 * width
        right = xx >= cx - 0.03 * width  # left side of the subject is missing
        head = (
            ((xx - cx) / (0.20 * width)) ** 2 + ((yy - 0.30 * height) / (0.16 * height)) ** 2 <= 1
        ) & right
        torso = (
            (yy > 0.42 * height) & (yy < 0.75 * height) & (np.abs(xx - cx) < 0.30 * width) & right
        )
        alpha[head | torso] = 0.95
        return alpha


@pytest.mark.asyncio
async def test_processor_rejects_corrupted_matte_with_face_box(store: TransactionFileStore) -> None:
    tx_id = "c" * 32
    store.create_transaction(tx_id, {"status": "CREATED"})
    store.write_artifact(tx_id, ArtifactType.SELECTED_ORIGINAL_CAPTURE, _jpeg(720, 1280))
    processor = PortraitProcessor(_settings(), store, segmentation=_CorruptedFaceSegmentation())
    with pytest.raises(PortraitProcessingError) as exc_info:
        await processor.process(_source(tx_id), tx_id, face_box_normalized=(0.35, 0.19, 0.30, 0.22))
    assert exc_info.value.code == PortraitErrorCode.PORTRAIT_QUALITY_FAILED
    # No corrupted portrait is promoted.
    assert not store.artifact_exists(tx_id, "portrait/processed.jpg")
    # Retryable quality outcome: NOT a technical error (pre-portrait state restored for retry).
    assert store.read_transaction_json(tx_id)["status"] == "CREATED"


@pytest.mark.asyncio
async def test_processor_success_with_face_box(store: TransactionFileStore) -> None:
    processor, tx_id = _prepare(store)
    result = await processor.process(
        _source(tx_id), tx_id, face_box_normalized=(0.35, 0.28, 0.30, 0.26)
    )
    assert result.status == "SUCCESS"
    assert store.artifact_exists(tx_id, "portrait/processed.jpg")


@pytest.mark.asyncio
async def test_refinement_damage_falls_back_to_raw_matte(store, monkeypatch) -> None:
    """If refinement would damage the primary face, the raw (already-gated) matte is used."""
    from app.portrait import processor as processor_module

    real_refine = processor_module.refine_matte

    def damaging_refine(alpha, face_box_normalized=None):
        out = real_refine(alpha, face_box_normalized=face_box_normalized)
        if face_box_normalized is not None:
            # Simulate destructive refinement: erase the left half of the face ROI.
            height, width = out.shape
            fx, fy, fw, fh = face_box_normalized
            x0, y0 = int(fx * width), int(fy * height)
            mid = x0 + int(fw * width) // 2
            out[y0 : int((fy + fh) * height), x0:mid] = 0.0
        return out

    monkeypatch.setattr(processor_module, "refine_matte", damaging_refine)
    processor, tx_id = _prepare(store)
    result = await processor.process(
        _source(tx_id), tx_id, face_box_normalized=(0.35, 0.28, 0.30, 0.26)
    )
    assert result.status == "SUCCESS"  # raw matte (which passed) used, no corruption promoted
    assert store.artifact_exists(tx_id, "portrait/processed.jpg")
