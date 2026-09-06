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


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson 95% score interval for a proportion k/n (M5 §53)."""
    if n <= 0:
        return None
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return (round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


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
    repetition: int | None = None


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
        return {"mean": 0.0, "median": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.mean(values), 1),
        "median": round(statistics.median(values), 1),
        "p90": round(_percentile(values, 0.90), 1),
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
    row: dict[str, Any] = {
        "class": label,
        "n": n,
        "correct": correct,
        "uncertain": uncertain,
        "error": errors,
        "spoof_to_live": spoof_to_live,
    }
    if label != "LIVE" and n:
        # Every percentage carries numerator/denominator (M5 §88).
        row["apcer_style_estimate"] = {
            "numerator": spoof_to_live,
            "denominator": n,
            "value": round(spoof_to_live / n, 4),
        }
        row["apcer_style_wilson_ci"] = wilson_interval(spoof_to_live, n)
    return row


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

    # BPCER-style: genuine samples not accepted as LIVE over genuine samples (M5 §57).
    # UNCERTAIN / QUALITY_FAILURE count as "not accepted as LIVE"; technical errors are reported
    # separately (M5 §56-57).
    bpcer_style = None
    genuine_non_accept = 0
    if live_total:
        genuine_non_accept = live_total - live_accept
        bpcer_style = round(genuine_non_accept / live_total, 4)

    latencies = [r.latency_ms for r in records if r.latency_ms is not None]

    return {
        "sample_count": len(records),
        "class_rows": class_rows,
        "spoof_to_live_total": spoof_accepted_as_live,
        "spoof_total": spoof_total,
        "apcer_style_overall": {
            "numerator": spoof_accepted_as_live,
            "denominator": spoof_total,
            "value": round(spoof_accepted_as_live / spoof_total, 4) if spoof_total else None,
        },
        "apcer_style_overall_wilson_ci": wilson_interval(spoof_accepted_as_live, spoof_total),
        "bpcer_style": bpcer_style,
        "bpcer_style_wilson_ci": wilson_interval(genuine_non_accept, live_total),
        "genuine_non_accept_rate": {
            "numerator": genuine_non_accept,
            "denominator": live_total,
            "value": bpcer_style,
        },
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
            "spoof_to_live": sum(
                1
                for r in bucket_records
                if classify_for(r.ground_truth) != VlmClassification.LIVE
                and r.predicted == VlmClassification.LIVE.value
            ),
        }
    return buckets


def high_confidence_errors(
    records: list[ResultRecord], threshold: float = 0.8
) -> list[dict[str, Any]]:
    """Wrong classifications at self_reported_confidence >= threshold (M5 §61).

    This is an exploratory analysis threshold, not a business rule.
    """
    rows = []
    for record in records:
        if (
            record.self_reported_confidence is not None
            and record.self_reported_confidence >= threshold
            and not is_uncertain(record)
            and not is_error(record)
            and not is_correct(record)
        ):
            rows.append(record.model_dump())
    return rows


def provider_reliability(records: list[ResultRecord]) -> dict[str, Any]:
    successful = sum(1 for r in records if not is_error(r))
    errors = error_counts(records)
    return {
        "successful_requests": successful,
        "total_requests": len(records),
        "timeouts": errors.get("PROVIDER_TIMEOUT", 0),
        "rate_limited": errors.get("PROVIDER_RATE_LIMITED", 0),
        "auth_errors": errors.get("PROVIDER_AUTH_ERROR", 0),
        "schema_failures": errors.get("SCHEMA_VALIDATION_ERROR", 0),
        "other_provider_errors": {
            code: count
            for code, count in errors.items()
            if code
            not in (
                "PROVIDER_TIMEOUT",
                "PROVIDER_RATE_LIMITED",
                "PROVIDER_AUTH_ERROR",
                "SCHEMA_VALIDATION_ERROR",
            )
        },
    }


def paired_strategy_comparison(records: list[ResultRecord]) -> dict[str, Any]:
    """Compare single-quality-v1 vs temporal-triad-v1 on the SAME samples (M5 §63)."""
    by_sample: dict[tuple[str, str, str], dict[str, ResultRecord]] = defaultdict(dict)
    for record in records:
        by_sample[(record.sample_id, record.provider, record.model)][record.frame_strategy] = record

    counts = {
        "both_correct": 0,
        "single_correct_triad_wrong": 0,
        "single_wrong_triad_correct": 0,
        "both_wrong": 0,
        "not_paired": 0,
    }
    paired_spoof_to_live: dict[str, int] = {"single": 0, "triad": 0}
    for by_strategy in by_sample.values():
        single = by_strategy.get("single-quality-v1")
        triad = by_strategy.get("temporal-triad-v1")
        if single is None or triad is None:
            counts["not_paired"] += 1
            continue
        s_ok = is_correct(single)
        t_ok = is_correct(triad)
        if s_ok and t_ok:
            counts["both_correct"] += 1
        elif s_ok and not t_ok:
            counts["single_correct_triad_wrong"] += 1
        elif not s_ok and t_ok:
            counts["single_wrong_triad_correct"] += 1
        else:
            counts["both_wrong"] += 1
        if (
            classify_for(single.ground_truth) != VlmClassification.LIVE
            and single.predicted == VlmClassification.LIVE.value
        ):
            paired_spoof_to_live["single"] += 1
        if (
            classify_for(triad.ground_truth) != VlmClassification.LIVE
            and triad.predicted == VlmClassification.LIVE.value
        ):
            paired_spoof_to_live["triad"] += 1

    return {"counts": counts, "paired_spoof_to_live": paired_spoof_to_live}


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
