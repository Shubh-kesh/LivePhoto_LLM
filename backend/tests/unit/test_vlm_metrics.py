"""VLM evaluation metrics tests (M4 §93-101, §105-106, §116)."""

from __future__ import annotations

from app.experiments.vlm.metrics import (
    ResultRecord,
    compute_metrics,
    error_counts,
    group_by_provider,
    group_by_strategy,
    is_correct,
    wilson_interval,
)


def _record(
    ground_truth: str,
    predicted: str | None,
    strategy: str = "single-quality-v1",
    provider: str = "gemini",
    model: str = "gemini-x",
    confidence: float | None = 0.9,
    error: str | None = None,
) -> ResultRecord:
    return ResultRecord(
        sample_id="s",
        ground_truth=ground_truth,
        predicted=predicted,
        provider=provider,
        model=model,
        prompt_version="vlm-passive-v3",
        frame_strategy=strategy,
        self_reported_confidence=confidence,
        latency_ms=1000,
        error=error,
    )


def test_correctness_by_class() -> None:
    live_correct = _record("LIVE", "LIVE")
    spoof_as_live = _record("SCREEN_MOBILE", "LIVE")
    assert is_correct(live_correct) is True
    assert is_correct(spoof_as_live) is False


def test_apcer_style_and_bpcer_style() -> None:
    records = [
        _record("LIVE", "LIVE"),
        _record("LIVE", "LIVE"),
        _record("LIVE", "SCREEN_REPLAY"),
        _record("SCREEN_MOBILE", "LIVE"),
        _record("SCREEN_MOBILE", "SCREEN_REPLAY"),
        _record("PRINT_PHOTO", "PRINT_ATTACK"),
        _record("PRINT_PHOTO", "LIVE"),
    ]
    metrics = compute_metrics(records)
    # spoof->LIVE: 2 of 4 attack samples.
    assert metrics["spoof_to_live_total"] == 2
    assert metrics["spoof_total"] == 4
    overall = metrics["apcer_style_overall"]
    assert overall["numerator"] == 2
    assert overall["denominator"] == 4
    assert overall["value"] == 0.5
    # BPCER-style: 1 of 3 genuine not accepted as LIVE.
    assert metrics["bpcer_style"] == round(1 / 3, 4)
    assert metrics["bpcer_style_wilson_ci"] is not None
    assert metrics["genuine_non_accept_rate"]["numerator"] == 1


def test_wilson_interval() -> None:
    # 0/25 -> upper bound is small but nonzero (M5 §54).
    ci = wilson_interval(0, 25)
    assert ci is not None
    assert ci[0] == 0.0
    assert ci[1] > 0.0
    # 25/25 -> lower bound below 1.
    ci_all = wilson_interval(25, 25)
    assert ci_all is not None
    assert ci_all[1] == 1.0
    assert ci_all[0] < 1.0
    assert wilson_interval(0, 0) is None


def test_per_class_rows_and_error_rates() -> None:
    records = [
        _record("LIVE", "LIVE"),
        _record("LIVE", None, error="PROVIDER_TIMEOUT"),
        _record("SCREEN_MOBILE", "UNCERTAIN"),
        _record("SCREEN_MOBILE", "SCREEN_REPLAY"),
    ]
    metrics = compute_metrics(records)
    rows = {row["class"]: row for row in metrics["class_rows"]}
    assert rows["SCREEN_MOBILE"]["n"] == 2
    assert rows["SCREEN_MOBILE"]["uncertain"] == 1
    assert metrics["uncertain_rate"] == 0.25
    assert metrics["technical_error_rate"] == 0.25
    assert error_counts(records) == {"PROVIDER_TIMEOUT": 1}


def test_confidence_buckets() -> None:
    records = [
        _record("LIVE", "LIVE", confidence=0.95),
        _record("SCREEN_MOBILE", "LIVE", confidence=0.95),  # wrong at high confidence
        _record("PRINT_PHOTO", "PRINT_ATTACK", confidence=0.4),
        _record("LIVE", "LIVE", confidence=None),
    ]
    metrics = compute_metrics(records)
    bucket = metrics["confidence_buckets"]["0.8-1.0"]
    assert bucket["n"] == 2
    assert bucket["correct"] == 1
    assert bucket["incorrect"] == 1


def test_group_by_strategy_and_provider() -> None:
    records = [
        _record("LIVE", "LIVE", strategy="single-quality-v1"),
        _record("LIVE", "LIVE", strategy="temporal-triad-v1"),
        _record("LIVE", "LIVE", strategy="temporal-triad-v1", provider="groq", model="groq-x"),
    ]
    by_strategy = group_by_strategy(records)
    assert set(by_strategy.keys()) == {"single-quality-v1", "temporal-triad-v1"}
    by_provider = group_by_provider(records)
    assert set(by_provider.keys()) == {"gemini:gemini-x", "groq:groq-x"}


def test_latency_stats() -> None:
    metrics = compute_metrics(
        [_record("LIVE", "LIVE", confidence=0.9)] * 0
        + [_record("LIVE", "LIVE", confidence=0.9)]
        + [_record("LIVE", "LIVE", confidence=0.9)]
    )
    assert metrics["latency_ms"]["mean"] == 1000.0
