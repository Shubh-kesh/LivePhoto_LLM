"""Frame selection strategies (M4 §16-19, §20, §22).

- ``single-quality-v1``: the single quality-selected frame only.
- ``temporal-triad-v1``: 3 quality-eligible frames nearest 25% / 50% / 75% of burst chronology.

Callers pass only eligible frames; if fewer than 3 eligible frames exist, the triad returns what
is available and the caller must return an experiment precondition result instead of fabricating
frames (M4 §18).
"""

from __future__ import annotations

from typing import Literal

FrameStrategy = Literal["single-quality-v1", "temporal-triad-v1"]

FRAME_STRATEGIES: dict[str, int] = {
    "single-quality-v1": 1,
    "temporal-triad-v1": 3,
}


def is_supported_strategy(strategy: str) -> bool:
    return strategy in FRAME_STRATEGIES


def expected_frame_count(strategy: str) -> int:
    return FRAME_STRATEGIES[strategy]


def select_single_frame[T](items: list[T]) -> list[T]:
    """Deterministic middle-item selection (M4 §17)."""
    if not items:
        return []
    return [items[len(items) // 2]]


def select_temporal_triad[T](items: list[T]) -> list[T]:
    """Pick the items nearest 25/50/75% of the (chronological) eligible list (M4 §18)."""
    n = len(items)
    if n == 0:
        return []
    if n < 3:
        return list(items)
    used: set[int] = set()
    for target in (0.25, 0.5, 0.75):
        index = round(target * (n - 1))
        while index in used:
            index = min(n - 1, index + 1)
        used.add(index)
    return [items[index] for index in sorted(used)]
