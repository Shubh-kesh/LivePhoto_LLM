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
import json
import time
from pathlib import Path

from app.core.config import Settings
from app.experiments.vlm.frame_selection import select_single_frame, select_temporal_triad
from app.experiments.vlm.manifest import DatasetSample, load_manifest
from app.experiments.vlm.metrics import (
    ResultRecord,
    compute_metrics,
    error_counts,
    group_by_provider,
    group_by_strategy,
)
from app.experiments.vlm.reports import (
    write_baseline_report,
    write_false_live_rejects,
    write_false_spoof_accepts,
    write_model_disagreements,
    write_results,
)
from app.experiments.vlm.service import ExperimentEvaluateRequest, VlmEvaluationService
from app.providers.vision import PROMPT_VERSION, VlmError, get_vision_provider
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
    parser = argparse.ArgumentParser(description="Run the M4 VLM baseline evaluation")
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
    samples: list[DatasetSample],
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
    progress: object = None,
) -> list[ResultRecord]:
    provider_model = get_vision_provider(settings, provider).info.model_id
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
                f"completed={len(results)}/{len(samples)} errors={errors} elapsed={elapsed:.1f}s"
            )

    async def run_one(sample: DatasetSample) -> None:
        nonlocal errors
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

    tasks = [asyncio.create_task(run_one(sample)) for sample in samples]
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

    def progress(message: str) -> None:
        print(f"[runner] {message}", flush=True)

    records = asyncio.run(
        evaluate_samples(
            samples,
            service,
            settings=settings,
            provider=args.provider,
            strategy=args.strategy,
            results_path=results_path,
            output_dir=output_dir,
            concurrency=args.concurrency,
            rps=args.rps,
            rerun=args.rerun,
            progress=progress,
        )
    )

    if records:
        metrics = compute_metrics(records)
        config = {
            "provider": args.provider,
            "strategy": args.strategy,
            "split": args.split,
            "run_id": time.strftime("%Y%m%d-%H%M%S"),
            "application_version": settings.app_version,
        }
        metrics["per_strategy"] = group_by_strategy(records)
        metrics["per_provider"] = group_by_provider(records)
        metrics["error_counts"] = error_counts(records)
        metrics["dataset_class_counts"] = {
            label: sum(1 for s in samples if s.label == label)
            for label in sorted({s.label for s in samples})
        }
        write_baseline_report(output_dir, config, metrics)
        write_false_spoof_accepts(output_dir, records)
        write_false_live_rejects(output_dir, records)
        write_model_disagreements(output_dir, records)
        print(f"[runner] baseline report: {output_dir / 'baseline_report.json'}")


if __name__ == "__main__":
    main()
