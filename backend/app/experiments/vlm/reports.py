"""Benchmark report writers (M4 §91-92, §117-120).

Only references and normalized fields are written — never image bytes. Reports live in git-ignored
artifacts/vlm-evaluation/.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.experiments.vlm.metrics import (
    ResultRecord,
    classify_for,
    is_correct,
    is_error,
    is_uncertain,
)
from app.providers.vision import VlmClassification


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_results(results_path: Path, records: list[ResultRecord]) -> None:
    write_jsonl(results_path, [r.model_dump() for r in records])


def write_false_spoof_accepts(output_dir: Path, records: list[ResultRecord]) -> None:
    rows = [
        r.model_dump()
        for r in records
        if classify_for(r.ground_truth) != VlmClassification.LIVE
        and not is_error(r)
        and r.predicted == VlmClassification.LIVE.value
    ]
    write_jsonl(output_dir / "false_spoof_accepts.jsonl", rows)


def write_false_live_rejects(output_dir: Path, records: list[ResultRecord]) -> None:
    rows = [
        r.model_dump()
        for r in records
        if r.ground_truth == "LIVE"
        and not is_error(r)
        and r.predicted != VlmClassification.LIVE.value
    ]
    write_jsonl(output_dir / "false_live_rejects.jsonl", rows)


def write_model_disagreements(output_dir: Path, records: list[ResultRecord]) -> None:
    grouped: dict[tuple[str, str], list[ResultRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.sample_id, record.frame_strategy)].append(record)
    rows = []
    for (sample_id, strategy), decisions in sorted(grouped.items()):
        distinct = {(d.provider, d.model): d for d in decisions}
        if len(distinct) <= 1:
            continue
        rows.append(
            {
                "sample_id": sample_id,
                "frame_strategy": strategy,
                "ground_truth": decisions[0].ground_truth,
                "decisions": [
                    {
                        "provider": decision.provider,
                        "model": decision.model,
                        "predicted": decision.predicted,
                        "self_reported_confidence": decision.self_reported_confidence,
                    }
                    for decision in distinct.values()
                ],
            }
        )
    write_jsonl(output_dir / "model_disagreements.jsonl", rows)


def write_baseline_report(
    output_dir: Path, config: dict[str, Any], metrics: dict[str, Any]
) -> None:
    report = {
        "run_configuration": config,
        "interpretation": {
            "disclaimer": (
                "Results are for this finite evaluation set only and are NOT a production accuracy "
                "claim. self_reported_confidence is not calibrated probability."
            ),
        },
        "metrics": metrics,
    }
    path = output_dir / "baseline_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summarize(records: list[ResultRecord]) -> dict[str, Any]:
    conclusive = sum(
        1 for r in records if not is_error(r) and r.predicted != VlmClassification.UNCERTAIN.value
    )
    return {
        "total": len(records),
        "conclusive": conclusive,
        "uncertain": sum(1 for r in records if is_uncertain(r)),
        "technical_errors": sum(1 for r in records if is_error(r)),
        "correct": sum(1 for r in records if is_correct(r)),
    }
