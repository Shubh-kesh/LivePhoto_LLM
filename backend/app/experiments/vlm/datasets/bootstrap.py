"""Dataset bootstrap (M5 §14-16, §22-29).

Takes a raw source manifest (local, git-ignored), maps labels to the canonical taxonomy, applies
deterministic diverse sampling per class, creates subject/session-disjoint dev/holdout splits,
copies the minimum necessary subset into the git-ignored output, and writes a validated
``manifest.jsonl`` with full traceability (source dataset/sample/label). No dataset files are ever
committed.

The bootstrap does NOT override the licensing decision: ``require_usable_dataset`` must pass first
(M5 §15).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.experiments.vlm.datasets.frame_extraction import (
    FRAME_EXTRACTION_VERSION,
    extract_video_frames,
    is_video,
)
from app.experiments.vlm.datasets.labelmap import map_label
from app.experiments.vlm.datasets.licensing import require_usable_dataset
from app.experiments.vlm.datasets.registry import find_dataset
from app.experiments.vlm.datasets.sampling import (
    SAMPLING_VERSION,
    SPLIT_VERSION,
    diverse_sample,
    split_dev_holdout,
)
from app.experiments.vlm.manifest import GroundTruthLabel


class RawSourceItem(BaseModel):
    sample_id: str
    source_dataset: str
    source_label: str
    frames: list[str] = Field(default_factory=list)
    subject_alias: str | None = None
    capture_device_class: str | None = None
    presentation_device_class: str | None = None
    presentation_border_visible: bool | None = None
    lighting: str | None = None
    prompt_injection: bool = False


@dataclass
class BootstrapConfig:
    dataset_name: str
    source_manifest: Path
    output_dir: Path
    samples_per_class: dict[str, int]
    holdout_fraction: float = 0.8
    seed: int = 42
    frame_extraction_version: str = FRAME_EXTRACTION_VERSION
    sampling_version: str = SAMPLING_VERSION
    split_version: str = SPLIT_VERSION


def load_raw_manifest(path: Path) -> list[RawSourceItem]:
    items: list[RawSourceItem] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                items.append(RawSourceItem.model_validate(json.loads(line)))
    return items


def _mapped_items(
    items: list[RawSourceItem],
) -> tuple[list[tuple[RawSourceItem, GroundTruthLabel]], list[dict[str, Any]]]:
    mapped: list[tuple[RawSourceItem, GroundTruthLabel]] = []
    dropped: list[dict[str, Any]] = []
    for item in items:
        canonical, ambiguous = map_label(item.source_label)
        if canonical is None:
            dropped.append(
                {
                    "sample_id": item.sample_id,
                    "source_label": item.source_label,
                    "reason": "ambiguous" if ambiguous else "unmapped",
                }
            )
            continue
        mapped.append((item, canonical))
    return mapped, dropped


def build_manifest(config: BootstrapConfig) -> Path:
    require_usable_dataset(config.dataset_name)

    items = load_raw_manifest(config.source_manifest)
    mapped, dropped = _mapped_items(items)

    by_class: dict[str, list[tuple[RawSourceItem, GroundTruthLabel]]] = {}
    for item, canonical in mapped:
        by_class.setdefault(canonical, []).append((item, canonical))

    selected: list[tuple[RawSourceItem, GroundTruthLabel]] = []
    for class_label, members in sorted(by_class.items()):
        k = config.samples_per_class.get(class_label, 0)
        chosen = diverse_sample(
            members,
            key=lambda pair: pair[0].subject_alias or pair[0].sample_id,
            k=k,
            seed=config.seed,
        )
        selected.extend(chosen)

    dev, holdout = split_dev_holdout(
        selected,
        key=lambda pair: pair[0].subject_alias or pair[0].sample_id,
        holdout_fraction=config.holdout_fraction,
        seed=config.seed,
    )

    samples_dir = config.output_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    descriptor = find_dataset(config.dataset_name)
    license_status = descriptor.license_state.value if descriptor else "UNCLEAR"
    usage_purpose = descriptor.usage_purpose if descriptor else "NON_COMMERCIAL_POC_RESEARCH"

    holdout_ids = {pair[0].sample_id for pair in holdout}

    rows: list[dict[str, Any]] = []
    for index, (item, canonical) in enumerate(dev + holdout, start=1):
        split_name: str = "holdout" if item.sample_id in holdout_ids else "dev"
        frames: list[str] = []
        for source_frame in item.frames:
            source_path = Path(source_frame)
            if is_video(source_path):
                extracted = extract_video_frames(source_path, samples_dir / item.sample_id)
                frames.extend(str(p.relative_to(config.output_dir)) for p in extracted)
            else:
                target = samples_dir / f"{item.sample_id}-{len(frames)}.jpg"
                shutil.copy2(source_path, target)
                frames.append(str(target.relative_to(config.output_dir)))
        rows.append(
            {
                "sample_id": f"{config.dataset_name}-{index:03d}",
                "source_dataset": item.source_dataset,
                "source_sample_id": item.sample_id,
                "source_label": item.source_label,
                "canonical_label": canonical,
                "label": canonical,
                "split": split_name,
                "subject_alias": item.subject_alias,
                "capture_device_class": item.capture_device_class,
                "presentation_device_class": item.presentation_device_class,
                "presentation_border_visible": item.presentation_border_visible,
                "lighting": item.lighting,
                "prompt_injection": item.prompt_injection,
                "license_status": license_status,
                "usage_purpose": usage_purpose,
                "frames": frames,
            }
        )

    manifest_path = config.output_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    sidecar = {
        "dataset_name": config.dataset_name,
        "sampling_seed": config.seed,
        "sampling_version": config.sampling_version,
        "split_version": config.split_version,
        "frame_extraction_version": config.frame_extraction_version,
        "holdout_fraction": config.holdout_fraction,
        "dropped_samples": dropped,
    }
    (config.output_dir / "bootstrap_metadata.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path
