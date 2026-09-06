"""Evaluation metrics (M4 §93-101, §105-106, §116).

Per-sample results are benchmark artifacts (never Prometheus metrics). The most important number is
``SPOOF -> LIVE`` per attack class (M4 §94), reported as an experimental APCER-style estimate, not
an ISO certification claim. `self_reported_confidence` is never treated as calibrated probability.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from app.experiments.vlm.manifest import DatasetSample
from app.providers.vision import VlmClassification, VlmErrorCode

LABEL_TO_CLASSIFICATION: dict[str, VlmClassification] = {
    "LIVE": VlmClassification.LIVE,
    "SCREEN_MOBILE": VlmClassification.SCREEN_REPLAY,
    "SCREEN_TABLET": VlmClassification.SCREEN_REPLAY,
    "SCREEN_LAPTOP": VlmClassification.SCREEN_REPLAY,
    "SCREEN_MONITOR": VlmClassification.SCREEN_REPLAY,
    "PRINT_PHOTO": VlmClassification.PRINT_ATTACK,
    "PRINT_NEWSPAPER": VlmClassification.PRINT_ATTACK,
    "PRINT_MAGAZINE": VlmClassification.PRINT_ATTACK,
}


class ResultRecord(BaseModel):
    sample_id: str
    ground_truth: str
    predicted: str | None
    attack_medium_predicted: str | None = None
    provider: str
    model: str
    prompt_version: str
    frame_strategy: str
    self_reported_confidence: float | None = None
    latency_ms: int | None = None
    error: str | None = None


def classify_for(label: str) -> VlmClassification:
    return LABEL_TO_CLASSIFICATION[label]


def is_error(record: ResultRecord) -> bool:
    return record.error is not None


def is_uncertain(record: ResultRecord) -> bool:
    return (not is_error(record)) and record.predicted == VlmClassification.UNCERTAIN.value


def is_correct(record: ResultRecord) -> bool:
    if is_error(record) or is_uncertain(record) or record.predicted is None:
        return False
    return record.predicted == classify_for(record.ground_truth).value


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = ordered[math.floor(index)]
    upper = ordered[math.ceil(index)]
    return lower if index.is_integer() else (lower + upper) / 2


def latency_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.mean(values), 1),
        "median": round(statistics.median(values), 1),
        "p95": round(_percentile(values, 0.95), 1),
        "max": round(max(values), 1),
    }


def _class_row(label: str, records: list[ResultRecord]) -> dict[str, Any]:
    n = len(records)
    correct = sum(1 for r in records if is_correct(r))
    uncertain = sum(1 for r in records if is_uncertain(r))
    errors = sum(1 for r in records if is_error(r))
    spoof_to_live = sum(
        1 for r in records if label != "LIVE" and r.predicted == VlmClassification.LIVE.value
    )
    return {
        "class": label,
        "n": n,
        "correct": correct,
        "uncertain": uncertain,
        "error": errors,
        "spoof_to_live": spoof_to_live,
        "apcer_style_estimate": round(spoof_to_live / n, 4) if n and label != "LIVE" else None,
    }


def compute_metrics(
    records: list[ResultRecord], samples: list[DatasetSample] | None = None
) -> dict[str, Any]:
    by_class = defaultdict(list)
    for record in records:
        by_class[record.ground_truth].append(record)

    class_rows = [_class_row(label, rows) for label, rows in sorted(by_class.items())]

    live_records = by_class.get("LIVE", [])
    live_accept = sum(
        1 for r in live_records if not is_error(r) and r.predicted == VlmClassification.LIVE.value
    )
    live_total = len(live_records)
    spoof_records = [r for label, rows in by_class.items() if label != "LIVE" for r in rows]
    spoof_total = len(spoof_records)
    spoof_accepted_as_live = sum(
        1 for r in spoof_records if r.predicted == VlmClassification.LIVE.value
    )

    conclusive = sum(
        1 for r in records if not is_error(r) and r.predicted != VlmClassification.UNCERTAIN.value
    )
    uncertain = sum(1 for r in records if is_uncertain(r))
    errors = sum(1 for r in records if is_error(r))

    # BPCER-style: genuine samples not accepted as LIVE over genuine samples.
    # Treatment of uncertain/quality-failure/errors: they count as "not accepted as LIVE" (M4 §96).
    bpcer_style = None
    if live_total:
        bpcer_style = round((live_total - live_accept) / live_total, 4)

    latencies = [r.latency_ms for r in records if r.latency_ms is not None]

    return {
        "sample_count": len(records),
        "class_rows": class_rows,
        "spoof_to_live_total": spoof_accepted_as_live,
        "spoof_total": spoof_total,
        "apcer_style_overall": round(spoof_accepted_as_live / spoof_total, 4)
        if spoof_total
        else None,
        "bpcer_style": bpcer_style,
        "live_precision": round(
            live_accept
            / max(1, sum(1 for r in records if r.predicted == VlmClassification.LIVE.value)),
            4,
        ),
        "live_recall": round(live_accept / live_total, 4) if live_total else None,
        "conclusive_rate": round(conclusive / len(records), 4) if records else None,
        "uncertain_rate": round(uncertain / len(records), 4) if records else None,
        "technical_error_rate": round(errors / len(records), 4) if records else None,
        "latency_ms": latency_stats([float(v) for v in latencies]),
        "confidence_buckets": _confidence_buckets(records),
    }


def _confidence_buckets(records: list[ResultRecord]) -> dict[str, dict[str, int]]:
    buckets: dict[str, dict[str, int]] = {}
    for lower, upper in [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]:
        bucket_records = [
            r
            for r in records
            if r.self_reported_confidence is not None
            and lower <= r.self_reported_confidence < upper
        ]
        buckets[f"{lower:.1f}-{upper:.1f}"] = {
            "n": len(bucket_records),
            "correct": sum(1 for r in bucket_records if is_correct(r)),
            "incorrect": sum(
                1
                for r in bucket_records
                if not is_correct(r) and not is_uncertain(r) and not is_error(r)
            ),
        }
    return buckets


def group_by_strategy(records: list[ResultRecord]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[ResultRecord]] = defaultdict(list)
    for record in records:
        grouped[record.frame_strategy].append(record)
    return {strategy: compute_metrics(rows) for strategy, rows in grouped.items()}


def group_by_provider(records: list[ResultRecord]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[ResultRecord]] = defaultdict(list)
    for record in records:
        grouped[f"{record.provider}:{record.model}"].append(record)
    return {key: compute_metrics(rows) for key, rows in sorted(grouped.items())}


def group_by_class_and_strategy(records: list[ResultRecord]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, dict[str, list[ResultRecord]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        grouped[record.frame_strategy][record.ground_truth].append(record)
    result: dict[str, list[dict[str, Any]]] = {}
    for strategy, classes in grouped.items():
        result[strategy] = [_class_row(label, rows) for label, rows in sorted(classes.items())]
    return result


def error_counts(records: list[ResultRecord]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        if record.error:
            counts[record.error] += 1
    return dict(sorted(counts.items()))


def vlm_error_enum_values() -> list[str]:
    return [code.value for code in VlmErrorCode]
