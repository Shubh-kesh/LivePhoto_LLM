"""M4 dataset evaluation runner CLI (M4 §88-90, §142-144).

Example:
    uv run python -m app.experiments.vlm.run \
      --manifest ../local-data/vlm-baseline/manifest.jsonl \
      --provider gemini \
      --strategy temporal-triad-v1 \
      --output ../artifacts/vlm-evaluation/run-001

Requires VLM_EXPERIMENT_ENABLED=true and a configured provider (or provider=mock). Supports safe
resume (sample_id/provider/model/prompt_version/strategy), bounded concurrency, requests-per-second
rate limiting, and graceful interrupt (results written incrementally).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path

from app.core.config import Settings
from app.experiments.vlm.datasets.frame_extraction import FRAME_EXTRACTION_VERSION
from app.experiments.vlm.datasets.sampling import SAMPLING_VERSION
from app.experiments.vlm.frame_selection import (
    expected_frame_count,
    select_single_frame,
    select_temporal_triad,
)
from app.experiments.vlm.manifest import DatasetSample, load_manifest
from app.experiments.vlm.metrics import (
    ResultRecord,
    compute_metrics,
    error_counts,
    group_by_provider,
    group_by_strategy,
    high_confidence_errors,
    paired_strategy_comparison,
    provider_reliability,
)
from app.experiments.vlm.reports import (
    summarize,
    write_baseline_report,
    write_baseline_report_md,
    write_confusion_matrix_csv,
    write_false_live_rejects,
    write_false_spoof_accepts,
    write_jsonl,
    write_m6_priority_analysis,
    write_model_disagreements,
    write_results,
)
from app.experiments.vlm.service import ExperimentEvaluateRequest, VlmEvaluationService
from app.providers.vision import (
    PROMPT_ID,
    PROMPT_VERSION,
    VLM_SCHEMA_VERSION,
    VlmError,
    get_vision_provider,
)
from app.providers.vision.models import ImageInput


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self._interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self._interval
        if wait > 0:
            await asyncio.sleep(wait)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the M5 VLM baseline evaluation")
    parser.add_argument("--manifest", required=True, help="path to manifest.jsonl")
    parser.add_argument(
        "--provider", required=True, help="vlm provider (gemini|groq|openrouter|mock)"
    )
    parser.add_argument(
        "--strategy", required=True, choices=["single-quality-v1", "temporal-triad-v1"]
    )
    parser.add_argument("--output", required=True, help="output directory (git-ignored)")
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    parser.add_argument("--limit", type=int, default=0, help="max samples to evaluate (0 = all)")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument(
        "--rps", type=float, default=0.0, help="requests per second (0 = unlimited)"
    )
    parser.add_argument("--rerun", action="store_true", help="re-evaluate completed runs")
    parser.add_argument("--dry-run", action="store_true", help="print expected calls, send nothing")
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicit opt-in to send images to the configured external provider (M5 §42)",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="hard request budget; REQUIRED for live runs (M5 §43)",
    )
    parser.add_argument("--dataset-name", default="", help="dataset name for run metadata")
    parser.add_argument(
        "--repetitions", type=int, default=0, help="repeat each of the first samples N times"
    )
    parser.add_argument("--repeatability-limit", type=int, default=10)
    return parser.parse_args()


def _sample_key(sample: DatasetSample, provider: str, model: str, strategy: str) -> str:
    return json.dumps([sample.sample_id, provider, model, PROMPT_VERSION, strategy], sort_keys=True)


def _load_completed(results_path: Path) -> set[str]:
    if not results_path.exists():
        return set()
    keys: set[str] = set()
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add(
                json.dumps(
                    [
                        data.get("sample_id"),
                        data.get("provider"),
                        data.get("model"),
                        data.get("prompt_version"),
                        data.get("frame_strategy"),
                    ],
                    sort_keys=True,
                )
            )
    return keys


async def evaluate_samples(
    items: list[tuple[DatasetSample, int | None]],
    service: VlmEvaluationService,
    *,
    settings: Settings,
    provider: str,
    strategy: str,
    results_path: Path,
    output_dir: Path,
    concurrency: int,
    rps: float,
    rerun: bool,
    max_requests: int | None = None,
    progress: object = None,
) -> list[ResultRecord]:
    provider_model = get_vision_provider(settings, provider).info.model_id
    if max_requests is not None:
        items = items[:max_requests]
    completed = set() if rerun else _load_completed(results_path)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    limiter = RateLimiter(rps)
    lock = asyncio.Lock()
    results: list[ResultRecord] = []
    errors = 0
    started = time.perf_counter()

    def log_progress() -> None:
        if callable(progress):
            elapsed = time.perf_counter() - started
            progress(
                f"completed={len(results)}/{len(items)} errors={errors} elapsed={elapsed:.1f}s"
            )

    async def run_one(pair: tuple[DatasetSample, int | None]) -> None:
        nonlocal errors
        sample, repetition = pair
        key = _sample_key(sample, provider, provider_model, strategy)
        async with semaphore:
            if key in completed:
                return
            await limiter.acquire()
            frames = _read_sample_frames(sample, strategy)
            record = ResultRecord(
                sample_id=sample.sample_id,
                ground_truth=sample.label,
                predicted=None,
                provider=provider,
                model=provider_model,
                prompt_version=PROMPT_VERSION,
                frame_strategy=strategy,
                repetition=repetition,
            )
            try:
                request = ExperimentEvaluateRequest(
                    strategy=strategy,
                    capture_config_version="capture-v1",
                    quality_config_version="quality-v1",
                    frame_selection_version=strategy,
                    provider=provider,
                    frames=frames,
                )
                result = await service.evaluate(request)
                record.predicted = result.classification
                record.attack_medium_predicted = result.attack_medium
                record.self_reported_confidence = result.self_reported_confidence
                record.latency_ms = result.latency_ms
                record.error = result.error.value if result.error else None
            except VlmError as exc:
                record.error = exc.code.value
                errors += 1
            async with lock:
                results.append(record)
                write_results(results_path, results)
            log_progress()

    tasks = [asyncio.create_task(run_one(pair)) for pair in items]
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        log_progress()

    return results


def _read_sample_frames(sample: DatasetSample, strategy: str) -> list[ImageInput]:
    items = [Path(path) for path in sample.frames]
    selected = (
        select_single_frame(items)
        if strategy == "single-quality-v1"
        else select_temporal_triad(items)
    )
    return [
        ImageInput(bytes=path.read_bytes(), mime_type="image/jpeg", sequence=index)
        for index, path in enumerate(selected)
    ]


def _git_info() -> tuple[str, bool]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
        return commit, dirty
    except Exception:
        return "unknown", True


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_run_flags(
    provider: str,
    live: bool,
    max_requests: int | None,
    expected_calls: int,
) -> str | None:
    """Return an error message if a live run is not safe to proceed (M5 §42-43)."""
    if provider != "mock":
        if not live:
            return (
                "REFUSING: sending images to an external provider requires --live/"
                "--confirm-external-provider (M5 §42)."
            )
        if max_requests is None:
            return "REFUSING: --max-requests is required for live runs (M5 §43)."
    if max_requests is not None and expected_calls > max_requests:
        return f"REFUSING: {expected_calls} calls exceeds --max-requests {max_requests}."
    return None


def main() -> None:
    args = _parse_args()
    settings = Settings()
    service = VlmEvaluationService(settings)
    samples = load_manifest(args.manifest)
    if args.split != "all":
        samples = [s for s in samples if s.split == args.split]
    if args.limit > 0:
        samples = samples[: args.limit]

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.jsonl"

    # Repeatability (M5 §64): run the first K samples N times with a repetition tag.
    items: list[tuple[DatasetSample, int | None]] = [(s, None) for s in samples]
    if args.repetitions > 0:
        repeat = samples[: args.repeatability_limit]
        items = items + [(s, rep) for rep in range(1, args.repetitions + 1) for s in repeat]

    expected_calls = len(items)

    def progress(message: str) -> None:
        print(f"[runner] {message}", flush=True)

    if args.dry_run:
        progress(
            f"DRY RUN: samples={len(samples)} provider={args.provider} "
            f"strategy={args.strategy} expected_api_calls={expected_calls} "
            f"images_transmitted={expected_calls * expected_frame_count(args.strategy)} "
            f"(no external calls made)"
        )
        return

    refusal = validate_run_flags(args.provider, args.live, args.max_requests, expected_calls)
    if refusal:
        raise SystemExit(refusal)

    commit, dirty = _git_info()
    run_id = time.strftime("%Y%m%d-%H%M%S")
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    records = asyncio.run(
        evaluate_samples(
            items,
            service,
            settings=settings,
            provider=args.provider,
            strategy=args.strategy,
            results_path=results_path,
            output_dir=output_dir,
            concurrency=args.concurrency,
            rps=args.rps,
            rerun=args.rerun,
            max_requests=args.max_requests,
            progress=progress,
        )
    )

    if records:
        metrics = compute_metrics(records)
        config = {
            "run_id": run_id,
            "git_commit_sha": commit,
            "dirty_working_tree": dirty,
            "dataset_name": args.dataset_name,
            "dataset_manifest_sha256": _sha256_of(Path(args.manifest)),
            "provider": args.provider,
            "model": get_vision_provider(settings, args.provider).info.model_id,
            "prompt_id": PROMPT_ID,
            "prompt_version": PROMPT_VERSION,
            "schema_version": VLM_SCHEMA_VERSION,
            "strategy": args.strategy,
            "split": args.split,
            "sampling_version": SAMPLING_VERSION,
            "frame_extraction_version": FRAME_EXTRACTION_VERSION,
            "application_version": settings.app_version,
            "started_at": started_at,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        metrics["per_strategy"] = group_by_strategy(records)
        metrics["per_provider"] = group_by_provider(records)
        metrics["error_counts"] = error_counts(records)
        metrics["provider_reliability"] = provider_reliability(records)
        metrics["paired_strategy"] = paired_strategy_comparison(records)
        metrics["dataset_class_counts"] = {
            label: sum(1 for s in samples if s.label == label)
            for label in sorted({s.label for s in samples})
        }
        metrics["high_confidence_error_count"] = len(high_confidence_errors(records))

        write_baseline_report(output_dir, config, metrics)
        write_baseline_report_md(output_dir, config, metrics)
        write_confusion_matrix_csv(output_dir, metrics)
        write_false_spoof_accepts(output_dir, records)
        write_false_live_rejects(output_dir, records)
        write_model_disagreements(output_dir, records)
        write_m6_priority_analysis(output_dir, metrics)
        write_jsonl(output_dir / "high_confidence_errors.jsonl", high_confidence_errors(records))
        (output_dir / "strategy_comparison.json").write_text(
            json.dumps(metrics["paired_strategy"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "provider_comparison.json").write_text(
            json.dumps(metrics["per_provider"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        if args.repetitions > 0:
            repeat_rows = [r.model_dump() for r in records if r.repetition is not None]
            write_jsonl(output_dir / "repeatability_results.jsonl", repeat_rows)

        injection_ids = {s.sample_id for s in samples if s.prompt_injection}
        if injection_ids:
            rows = [r.model_dump() for r in records if r.sample_id in injection_ids]
            write_jsonl(output_dir / "prompt_injection_results.jsonl", rows)

        run_metadata = {"run_metadata": config, "summary": summarize(records)}
        (output_dir / "run_metadata.json").write_text(
            json.dumps(run_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[runner] baseline report: {output_dir / 'baseline_report.json'}")


if __name__ == "__main__":
    main()
