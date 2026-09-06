"""Frame selection strategy tests (M4 §16-19)."""

from __future__ import annotations

from app.experiments.vlm.frame_selection import (
    expected_frame_count,
    is_supported_strategy,
    select_single_frame,
    select_temporal_triad,
)


def test_supported_strategies() -> None:
    assert is_supported_strategy("single-quality-v1")
    assert is_supported_strategy("temporal-triad-v1")
    assert not is_supported_strategy("provider-max-v1")
    assert expected_frame_count("single-quality-v1") == 1
    assert expected_frame_count("temporal-triad-v1") == 3


def test_single_selects_deterministic_middle() -> None:
    assert select_single_frame(["a", "b", "c", "d", "e"]) == ["c"]
    assert select_single_frame([]) == []


def test_triad_selects_near_25_50_75_percent() -> None:
    frames = list(range(100))
    selected = select_temporal_triad(frames)
    assert len(selected) == 3
    # Indexes chosen nearest 25/50/75% of the 100-frame chronology.
    assert selected == [25, 50, 74]


def test_triad_returns_available_when_fewer_than_three() -> None:
    # Do not fabricate frames when fewer than 3 eligible exist (M4 §18).
    assert select_temporal_triad(["a", "b"]) == ["a", "b"]
    assert select_temporal_triad([]) == []


def test_triad_is_deterministic() -> None:
    frames = ["a", "b", "c", "d", "e", "f", "g", "h"]
    assert select_temporal_triad(frames) == select_temporal_triad(frames)
