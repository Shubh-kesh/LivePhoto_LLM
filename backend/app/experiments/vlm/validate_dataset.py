"""Dataset validation (M5 §30-33).

Validates a generated manifest: unique sample IDs, allowed labels/splits, file existence within the
approved dataset root (path-traversal reject), JPEG/image validity, frame counts, exact-duplicate
detection via SHA-256, and metadata schema. Produces ``dataset_validation.json`` (no image bytes).
"""

from __future__ import annotations

import hashlib
import json
import typing
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.experiments.vlm.manifest import DatasetSample, GroundTruthLabel

ALLOWED_LABELS = set(typing.get_args(GroundTruthLabel))
ALLOWED_SPLITS = {"dev", "holdout"}


class DatasetValidationError(Exception):
    pass


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_jpeg(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8\xff")


def validate_image(path: Path) -> bool:
    data = path.read_bytes()
    if not _is_jpeg(data):
        return False
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return False
    return True


def validate_manifest(manifest_path: Path, dataset_root: Path | None = None) -> dict[str, Any]:
    root = (dataset_root or manifest_path.parent).resolve()
    seen_ids: set[str] = set()
    seen_hashes: dict[str, list[str]] = {}
    missing_files: list[str] = []
    invalid_images: list[str] = []
    duplicates: list[dict[str, Any]] = []
    errors: list[str] = []
    class_counts: dict[str, int] = {}
    split_counts: dict[str, int] = {}
    sources: set[str] = set()

    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                sample = DatasetSample.model_validate(json.loads(line))
            except ValidationError as exc:
                errors.append(f"line {line_no}: schema error: {exc}")
                continue

            if sample.sample_id in seen_ids:
                errors.append(f"line {line_no}: duplicate sample_id '{sample.sample_id}'")
            seen_ids.add(sample.sample_id)

            if sample.label not in ALLOWED_LABELS:
                errors.append(f"line {line_no}: invalid label '{sample.label}'")
            if sample.split not in (None, *ALLOWED_SPLITS):
                errors.append(f"line {line_no}: invalid split '{sample.split}'")

            class_counts[sample.label] = class_counts.get(sample.label, 0) + 1
            if sample.split:
                split_counts[sample.split] = split_counts.get(sample.split, 0) + 1
            if sample.source_dataset:
                sources.add(sample.source_dataset)

            if not sample.frames:
                errors.append(f"line {line_no}: sample has no frames")

            for frame in sample.frames:
                path = (root / frame).resolve()
                if not path.is_relative_to(root):
                    errors.append(f"line {line_no}: path traversal rejected: '{frame}'")
                    continue
                if not path.exists():
                    missing_files.append(frame)
                    continue
                if not validate_image(path):
                    invalid_images.append(frame)
                    continue
                digest = sha256_of(path)
                seen_hashes.setdefault(digest, []).append(sample.sample_id)

    for digest, sample_ids in seen_hashes.items():
        if len(sample_ids) > 1:
            duplicates.append({"sha256": digest, "sample_ids": sorted(set(sample_ids))})

    report = {
        "manifest": str(manifest_path),
        "total_samples": len(seen_ids),
        "class_counts": dict(sorted(class_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "source_datasets": sorted(sources),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "missing_files": missing_files[:100],
        "missing_file_count": len(missing_files),
        "invalid_images": invalid_images[:100],
        "invalid_image_count": len(invalid_images),
        "validation_errors": errors[:100],
        "validation_error_count": len(errors),
        "license_status": "REVIEWED_IN_BOOTSTRAP",
    }
    return report


def write_validation_report(output_dir: Path, report: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "dataset_validation.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate an M5 dataset manifest (M5 §30-33)")
    parser.add_argument("--manifest", required=True, help="path to manifest.jsonl")
    parser.add_argument(
        "--root", default=None, help="approved dataset root (default: manifest dir)"
    )
    parser.add_argument("--output", required=True, help="directory for dataset_validation.json")
    args = parser.parse_args()

    report = validate_manifest(Path(args.manifest), Path(args.root) if args.root else None)
    out = write_validation_report(Path(args.output), report)
    print(f"[validate_dataset] report: {out}")
    if (
        report["validation_error_count"]
        or report["missing_file_count"]
        or report["invalid_image_count"]
    ):
        print(
            f"[validate_dataset] issues: errors={report['validation_error_count']} "
            f"missing={report['missing_file_count']} invalid={report['invalid_image_count']}"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
