"""Deterministic video-frame extraction (M5 §19).

LivePhoto evaluates photo frames, not videos. For video datasets we extract frames at 25/50/75% of
duration (frame-extraction-v1); extraction is deterministic and never random. If ffmpeg is
unavailable, extraction raises a clear error (still-image datasets need no extraction).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FRAME_EXTRACTION_VERSION = "frame-extraction-v1"

#: Fractions of video duration at which frames are extracted.
FRAME_TIMESTAMPS = (0.25, 0.5, 0.75)


def extraction_timestamps() -> tuple[float, ...]:
    return FRAME_TIMESTAMPS


def is_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv", ".avi"}


def extract_video_frames(video_path: Path, output_dir: Path) -> list[Path]:
    """Extract frames at 25/50/75% of duration using ffmpeg (deterministic)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg is required to extract frames from video datasets; install it or use a "
            "still-image dataset."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        [ffmpeg, "-i", str(video_path)],
        capture_output=True,
        text=True,
    )
    duration = None
    for line in (probe.stderr or "").splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            try:
                h, m, s = (float(p) for p in parts)
            except ValueError:
                break
            duration = h * 3600 + m * 60 + s
            break
    if duration is None or duration <= 0:
        raise RuntimeError(f"could not read duration for {video_path}")

    frames: list[Path] = []
    for index, fraction in enumerate(FRAME_TIMESTAMPS):
        target = output_dir / f"{video_path.stem}-{index:02d}.jpg"
        subprocess.run(
            [
                ffmpeg,
                "-ss",
                f"{fraction * duration:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-y",
                str(target),
            ],
            capture_output=True,
        )
        if target.exists():
            frames.append(target)
    if not frames:
        raise RuntimeError(f"no frames extracted from {video_path}")
    return frames
