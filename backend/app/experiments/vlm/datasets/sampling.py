"""Deterministic sampling, diversity and dataset splits (M5 §25-28).

- Seeded sampling so runs are reproducible; ``sampling_seed`` and ``sampling_version`` are
  recorded.
- Diversity: when subject/device metadata exists, sample across distinct values rather than the
  first N files.
- Splits are subject/session-disjoint where a key is available (M5 §27); the holdout is not tuned
  against.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence

SAMPLING_VERSION = "sampling-v1"
SPLIT_VERSION = "split-v1"


def seeded_sample[T](items: Sequence[T], k: int, seed: int) -> list[T]:
    """Deterministic sample of ``k`` items (fewer if not enough)."""
    if k <= 0:
        return []
    rng = random.Random(seed)
    return rng.sample(list(items), min(k, len(items)))


def diverse_sample[T](
    items: Sequence[T],
    key: Callable[[T], str],
    k: int,
    seed: int,
) -> list[T]:
    """Sample ``k`` items while spreading across distinct ``key`` groups (round-robin)."""
    if k <= 0 or not items:
        return []
    groups: dict[str, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    order = sorted(groups)
    rng = random.Random(seed)
    for group_key in order:
        rng.shuffle(groups[group_key])
    result: list[T] = []
    index = 0
    while len(result) < k:
        advanced = False
        for group_key in order:
            if index < len(groups[group_key]):
                result.append(groups[group_key][index])
                if len(result) >= k:
                    return result
                advanced = True
        if not advanced:
            break
        index += 1
    return result


def split_dev_holdout[T](
    items: Sequence[T],
    *,
    key: Callable[[T], str],
    holdout_fraction: float,
    seed: int,
) -> tuple[list[T], list[T]]:
    """Subject/session-disjoint dev/holdout split (M5 §27-28)."""
    groups: dict[str, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    group_keys = sorted(groups)
    rng = random.Random(seed)
    rng.shuffle(group_keys)
    holdout_count = max(1, round(len(group_keys) * holdout_fraction))
    holdout_keys = set(group_keys[:holdout_count])
    dev: list[T] = []
    holdout: list[T] = []
    for group_key, members in groups.items():
        if group_key in holdout_keys:
            holdout.extend(members)
        else:
            dev.extend(members)
    return dev, holdout


def iter_unique_sources[T](items: Iterable[T], key: Callable[[T], str]) -> list[str]:
    return sorted({key(item) for item in items})
