"""Dataset manifest loading (M4 §82-86, §112-115).

Manifest is local and git-ignored. Ground truth comes from the manifest labels, never from
filenames or VLM output. Non-identifying metadata only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

GroundTruthLabel = Literal[
    "LIVE",
    "SCREEN_MOBILE",
    "SCREEN_TABLET",
    "SCREEN_LAPTOP",
    "SCREEN_MONITOR",
    "PRINT_PHOTO",
    "PRINT_NEWSPAPER",
    "PRINT_MAGAZINE",
]


class DatasetSample(BaseModel):
    sample_id: str
    label: GroundTruthLabel
    attack_medium: str = "NONE"
    frames: list[str] = Field(default_factory=list)
    device_class: str | None = None
    environment: str | None = None
    split: Literal["dev", "holdout"] | None = None

    # M5 traceability (M4 §21): preserve original dataset/source label for every row.
    source_dataset: str | None = None
    source_sample_id: str | None = None
    source_label: str | None = None
    canonical_label: GroundTruthLabel | None = None
    subject_alias: str | None = None
    capture_device_class: str | None = None
    presentation_device_class: str | None = None
    presentation_border_visible: bool | None = None
    lighting: str | None = None
    prompt_injection: bool = False


def load_manifest(path: str | Path) -> list[DatasetSample]:
    """Load a JSONL manifest; frame paths are resolved relative to the manifest directory."""
    manifest_path = Path(path)
    base = manifest_path.parent
    samples: list[DatasetSample] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            raw["frames"] = [str((base / frame).resolve()) for frame in raw.get("frames", [])]
            samples.append(DatasetSample.model_validate(raw))
    return samples
