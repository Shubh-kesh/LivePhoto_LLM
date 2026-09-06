"""Axon public face-anti-spoofing sample downloader (M5 continuation).

Downloads the officially published public sample subset (Axon Labs / AxonData on Hugging Face,
CC BY-NC 4.0) under the NON_COMMERCIAL_POC_RESEARCH purpose into the git-ignored dataset root and
writes a raw manifest consumed by ``bootstrap.py``.

Files are never committed; no PII is recorded (only opaque file stems).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.experiments.vlm.datasets.registry import DatasetDescriptor, registry

BASE_URL = "https://huggingface.co/datasets/AxonData/face-anti-spoofing-dataset/resolve/main"

#: class -> list of relative paths to download.
SUBSET: dict[str, list[str]] = {
    "live": [
        f"Selfies/Selfie_{n}.jpg"
        for n in [
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
        ]
    ],
    "mobile": [
        f"Replay_mobile_attacks/Galaxy_a54-Pixel7/{name}"
        for name in [
            "20241126_030439.mp4",
            "20241126_030501.mp4",
            "20241126_030523.mp4",
            "20241126_030546.mp4",
            "20241126_030612.mp4",
            "20241126_030629.mp4",
            "20241126_030652.mp4",
            "20241126_030713.mp4",
            "20241126_030745.mp4",
            "20241126_030805.mp4",
        ]
    ],
    "screen_display": [
        f"Replay_display_attacks/Screen/{name}"
        for name in [
            "20240823_194131.mp4",
            "20240823_194241.mp4",
            "IMG_5915.MOV",
            "IMG_5987.MOV",
            "VID_20240823_171603.mp4",
        ]
    ],
}

CAPTURE_DEVICE_BY_SOURCE: dict[str, str] = {
    "live": "mobile",
    "mobile": "mobile",
    "screen_display": "unknown",
}
PRESENTATION_DEVICE_BY_SOURCE: dict[str, str] = {
    "live": "NONE",
    "mobile": "mobile",
    "screen_display": "display",
}


def descriptor() -> DatasetDescriptor:
    return registry()["axon-face-anti-spoofing-sample"]


def download_axon_subset(output_dir: Path, client: httpx.Client | None = None) -> Path:
    """Download the subset, return the raw manifest path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    download_root = output_dir / "source"
    download_root.mkdir(parents=True, exist_ok=True)

    own_client = client is None
    http = client or httpx.Client(timeout=120.0, follow_redirects=True)

    rows = []
    for source_label, paths in SUBSET.items():
        for relative in paths:
            target = download_root / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with http.stream("GET", f"{BASE_URL}/{relative}?download=true") as response:
                    response.raise_for_status()
                    with target.open("wb") as handle:
                        for chunk in response.iter_bytes(chunk_size=1 << 20):
                            handle.write(chunk)
            rows.append(
                {
                    "sample_id": relative.split("/")[-1].split(".")[0],
                    "source_dataset": descriptor().name,
                    "source_label": source_label,
                    "frames": [str(target)],
                    "subject_alias": relative.split("/")[-1].split(".")[0],
                    "capture_device_class": CAPTURE_DEVICE_BY_SOURCE[source_label],
                    "presentation_device_class": PRESENTATION_DEVICE_BY_SOURCE[source_label],
                }
            )

    if own_client:
        http.close()

    manifest_path = output_dir / "raw_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return manifest_path
