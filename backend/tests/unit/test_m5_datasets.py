"""M5 dataset tooling tests (M5 §100): registry, licensing, sampling, splits, label mapping,
bootstrap guard, manifest validation, frame extraction policy."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from app.experiments.vlm.datasets.frame_extraction import (
    FRAME_EXTRACTION_VERSION,
    extraction_timestamps,
    is_video,
)
from app.experiments.vlm.datasets.labelmap import map_label
from app.experiments.vlm.datasets.licensing import (
    DatasetLicenseError,
    evaluate_dataset,
    require_usable_dataset,
)
from app.experiments.vlm.datasets.registry import (
    LicenseState,
    is_usable_for_external_vlm,
    registry,
)
from app.experiments.vlm.datasets.sampling import (
    diverse_sample,
    seeded_sample,
    split_dev_holdout,
)
from app.experiments.vlm.validate_dataset import validate_manifest, write_validation_report


def test_known_datasets_have_honest_license_state() -> None:
    reg = registry()
    for name in (
        "celebA-spoof",
        "replay-attack",
        "replay-mobile",
        "oulu-npu",
        "siw",
        "axon-sample",
    ):
        assert name in reg, name
        descriptor = reg[name]
        # None is marked ALLOWED without explicit authorization; most are research-only.
        assert descriptor.license_state in (
            LicenseState.NOT_ALLOWED,
            LicenseState.UNCLEAR,
            LicenseState.REQUIRES_APPROVAL,
        )
    assert is_usable_for_external_vlm(reg["replay-attack"]) is False


def test_evaluate_dataset_reports_restricted_usage() -> None:
    _, decision = evaluate_dataset("replay-attack")
    assert "NOT_ALLOWED" in decision


def test_require_usable_dataset_blocks_restricted() -> None:
    with pytest.raises(DatasetLicenseError):
        require_usable_dataset("replay-attack")


def test_require_usable_dataset_blocks_unknown() -> None:
    with pytest.raises(DatasetLicenseError):
        require_usable_dataset("not-a-real-dataset")


def test_seeded_sampling_is_deterministic() -> None:
    items = list(range(100))
    assert seeded_sample(items, 10, seed=7) == seeded_sample(items, 10, seed=7)
    assert len(seeded_sample(items, 10, seed=7)) == 10
    all_items = seeded_sample(items, 200, seed=7)
    assert len(all_items) == 100 and set(all_items) == set(items)  # k > len -> all


def test_diverse_sample_spreads_across_subjects() -> None:
    items = [f"subject-{i % 5}-{i}" for i in range(50)]
    picked = diverse_sample(items, key=lambda s: s.split("-")[1], k=10, seed=1)
    subjects = {s.split("-")[1] for s in picked}
    assert len(subjects) >= 4


def test_split_is_subject_disjoint() -> None:
    items = [f"subject-{i}-frame-{j}" for i in range(10) for j in range(4)]
    dev, holdout = split_dev_holdout(
        items,
        key=lambda s: s.split("-")[0],
        holdout_fraction=0.8,
        seed=1,
    )
    dev_subjects = {s.split("-")[0] for s in dev}
    holdout_subjects = {s.split("-")[0] for s in holdout}
    assert not (dev_subjects & holdout_subjects)


def test_label_mapping() -> None:
    assert map_label("Phone") == ("SCREEN_MOBILE", False)
    assert map_label("Laptop_replay") == ("SCREEN_LAPTOP", False)
    assert map_label("A4") == ("PRINT_PHOTO", False)
    assert map_label("Live") == ("LIVE", False)
    canonical, ambiguous = map_label("screen_monitor_or_laptop")
    assert canonical is None
    assert ambiguous is True
    assert map_label("totally-unknown") == (None, True)


def test_frame_extraction_policy() -> None:
    assert extraction_timestamps() == (0.25, 0.5, 0.75)
    assert is_video(Path("clip.mp4")) is True
    assert is_video(Path("photo.jpg")) is False
    assert FRAME_EXTRACTION_VERSION == "frame-extraction-v1"


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (100, 100, 100)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _write_image(path: Path, data: bytes | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else _jpeg_bytes())


def _build_dataset(tmp_path: Path) -> Path:
    samples_dir = tmp_path / "samples"
    _write_image(samples_dir / "s1-a.jpg")
    _write_image(samples_dir / "s1-b.jpg")
    _write_image(samples_dir / "s2-a.jpg")
    _write_image(samples_dir / "s2-b.jpg")
    _write_image(samples_dir / "dup-a.jpg", _jpeg_bytes())
    _write_image(samples_dir / "dup-b.jpg", _jpeg_bytes())
    _write_image(samples_dir / "bad.jpg", b"not an image")
    rows = [
        {
            "sample_id": "s1",
            "label": "LIVE",
            "split": "dev",
            "source_dataset": "synthetic",
            "frames": ["samples/s1-a.jpg", "samples/s1-b.jpg"],
        },
        {
            "sample_id": "s2",
            "label": "SCREEN_MOBILE",
            "split": "holdout",
            "source_dataset": "synthetic",
            "frames": ["samples/s2-a.jpg", "samples/s2-b.jpg"],
        },
        {
            "sample_id": "s3",
            "label": "SCREEN_LAPTOP",
            "split": "holdout",
            "source_dataset": "synthetic",
            "frames": ["samples/dup-a.jpg"],
        },
        {
            "sample_id": "s4",
            "label": "PRINT_PHOTO",
            "split": "holdout",
            "source_dataset": "synthetic",
            "frames": ["samples/dup-b.jpg"],
        },
        {
            "sample_id": "s5",
            "label": "LIVE",
            "split": "holdout",
            "source_dataset": "synthetic",
            "frames": ["samples/bad.jpg"],
        },
        {
            "sample_id": "s6",
            "label": "LIVE",
            "split": "holdout",
            "source_dataset": "synthetic",
            "frames": ["samples/missing.jpg"],
        },
        {
            "sample_id": "s7",
            "label": "LIVE",
            "split": "holdout",
            "source_dataset": "synthetic",
            "frames": ["../escape.jpg"],
        },
    ]
    manifest = tmp_path / "manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return manifest


def test_validate_manifest_reports_counts_duplicates_and_traversal(tmp_path: Path) -> None:
    manifest = _build_dataset(tmp_path)
    report = validate_manifest(manifest, dataset_root=tmp_path)
    assert report["total_samples"] == 7
    assert report["class_counts"]["LIVE"] == 4
    assert report["split_counts"]["holdout"] == 6
    assert report["duplicate_count"] == 1  # dup-a/dup-b identical
    assert "samples/missing.jpg" in report["missing_files"]
    assert "samples/bad.jpg" in report["invalid_images"]
    assert any("path traversal" in e for e in report["validation_errors"])


def test_validation_report_written_without_images(tmp_path: Path) -> None:
    manifest = _build_dataset(tmp_path)
    report = validate_manifest(manifest, dataset_root=tmp_path)
    out = write_validation_report(tmp_path / "out", report)
    content = out.read_text()
    data = json.loads(content)
    assert data["total_samples"] == 7
    # No image bytes (JPEG signature/base64) are ever written.
    assert "\xff\xd8" not in content
    assert "base64" not in content
