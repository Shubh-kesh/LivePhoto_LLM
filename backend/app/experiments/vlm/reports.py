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


def write_confusion_matrix_csv(output_dir: Path, metrics: dict[str, Any]) -> None:
    path = output_dir / "confusion_matrix.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [["class", "n", "correct", "uncertain", "error", "spoof_to_live"]]
    for row in metrics.get("class_rows", []):
        rows.append(
            [
                str(row.get("class", "")),
                str(row.get("n", 0)),
                str(row.get("correct", 0)),
                str(row.get("uncertain", 0)),
                str(row.get("error", 0)),
                str(row.get("spoof_to_live", 0)),
            ]
        )
    path.write_text("\n".join(",".join(r) for r in rows) + "\n", encoding="utf-8")


def write_baseline_report_md(
    output_dir: Path, config: dict[str, Any], metrics: dict[str, Any]
) -> None:
    """Human-readable markdown report; every percentage carries numerator/denominator (M5 §88)."""
    path = output_dir / "baseline_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    def pct(numerator: int, denominator: int) -> str:
        if denominator == 0:
            return "n/a (0)"
        return f"{numerator}/{denominator} = {numerator / denominator * 100:.1f}%"

    lines: list[str] = [
        "# LivePhoto VLM Baseline Report (M5)",
        "",
        "## Run configuration",
    ]
    for key, value in sorted(config.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "> This is a finite evaluation set only; NOT a production accuracy claim. "
            "self_reported_confidence is not calibrated probability.",
            "",
            "## Per-class results",
            "| class | n | correct | uncertain | error | spoof->LIVE | APCER-style (CI) |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in metrics.get("class_rows", []):
        est = row.get("apcer_style_estimate") or {}
        ci = row.get("apcer_style_wilson_ci")
        ci_text = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "n/a"
        lines.append(
            f"| {row['class']} | {row['n']} | {row['correct']} | {row['uncertain']} | "
            f"{row['error']} | {row['spoof_to_live']} | "
            f"{pct(est.get('numerator', 0), est.get('denominator', 0))} {ci_text} |"
        )

    lines.extend(["", "## Overall"])
    overall = metrics.get("apcer_style_overall") or {}
    lines.append(
        f"- SPOOF -> LIVE (overall): "
        f"{pct(overall.get('numerator', 0), overall.get('denominator', 0))}"
    )
    gnar = metrics.get("genuine_non_accept_rate") or {}
    lines.append(
        f"- Genuine non-accept rate: {pct(gnar.get('numerator', 0), gnar.get('denominator', 0))}"
    )
    lines.append(f"- Uncertain rate: {metrics.get('uncertain_rate')}")
    lines.append(f"- Conclusive rate: {metrics.get('conclusive_rate')}")
    lines.append(f"- Technical error rate: {metrics.get('technical_error_rate')}")
    lines.append(f"- Latency (ms): {metrics.get('latency_ms')}")

    if metrics.get("per_strategy"):
        lines.extend(["", "## Per strategy"])
        for strategy, m in metrics.get("per_strategy", {}).items():
            s_overall = m.get("apcer_style_overall") or {}
            g = m.get("genuine_non_accept_rate") or {}
            lines.append(
                f"- {strategy}: spoof->LIVE "
                f"{pct(s_overall.get('numerator', 0), s_overall.get('denominator', 0))}, "
                f"genuine non-accept {pct(g.get('numerator', 0), g.get('denominator', 0))}"
            )

    if metrics.get("per_provider"):
        lines.extend(["", "## Per provider:model"])
        for key, m in metrics.get("per_provider", {}).items():
            s_overall = m.get("apcer_style_overall") or {}
            lines.append(
                f"- {key}: spoof->LIVE "
                f"{pct(s_overall.get('numerator', 0), s_overall.get('denominator', 0))}"
            )

    if metrics.get("confidence_buckets"):
        lines.extend(
            [
                "",
                "## Confidence buckets (self_reported_confidence)",
                "| bucket | n | correct | incorrect | spoof->LIVE |",
                "|---|---|---|---|---|",
            ]
        )
        for bucket, counts in metrics.get("confidence_buckets", {}).items():
            lines.append(
                f"| {bucket} | {counts['n']} | {counts['correct']} | "
                f"{counts['incorrect']} | {counts['spoof_to_live']} |"
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_m6_priority_analysis(output_dir: Path, metrics: dict[str, Any]) -> None:
    """Generate the M6 priority analysis from real results (M5 §81-82)."""
    path = output_dir / "m6_priority_analysis.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# M6 Priority Analysis (M5 evidence)",
        "",
        "Based only on measured results in this run. Priorities are ranked by the observed",
        "SPOOF -> LIVE rate per attack class (M5 §81-82).",
        "",
    ]
    rows = [r for r in metrics.get("class_rows", []) if r.get("class") != "LIVE"]
    rows.sort(key=lambda r: -(r.get("spoof_to_live", 0) or 0) / max(1, r.get("n", 1)))
    if not rows:
        lines.append("No attack-class samples were evaluated in this run.")
    for row in rows:
        est = row.get("apcer_style_estimate") or {}
        lines.append(
            f"## {row['class']}: {row['spoof_to_live']}/{row['n']} attacks classified LIVE "
            f"({est.get('value', 0) or 0:.1%} APCER-style)"
        )
        lines.append("")
        lines.append("- Priority level: HIGH if any spoof->LIVE observed, otherwise LOW.")
        lines.append("")
    lines.extend(
        [
            "## Recommendation",
            "",
            "Do not prescribe a specific M6 technology (e.g., YOLO) a priori; choose the layer",
            "addresses the highest observed failure class (device/screen/print/dedicated PAD)",
            "based on this evidence (M5 §82).",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
