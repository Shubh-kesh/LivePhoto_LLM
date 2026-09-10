"""M5 metrics/runner tests (M5 §100): Wilson CI, high-confidence errors, provider reliability,
paired strategy comparison, run-flag guards."""

from __future__ import annotations

from app.experiments.vlm.metrics import (
    ResultRecord,
    high_confidence_errors,
    paired_strategy_comparison,
    provider_reliability,
    wilson_interval,
)
from app.experiments.vlm.run import validate_run_flags


def _record(
    sample_id: str,
    ground_truth: str,
    predicted: str | None,
    strategy: str,
    confidence: float | None = 0.9,
    error: str | None = None,
    repetition: int | None = None,
) -> ResultRecord:
    return ResultRecord(
        sample_id=sample_id,
        ground_truth=ground_truth,
        predicted=predicted,
        provider="gemini",
        model="gemini-x",
        prompt_version="vlm-passive-v2",
        frame_strategy=strategy,
        self_reported_confidence=confidence,
        latency_ms=1000,
        error=error,
        repetition=repetition,
    )


def test_wilson_interval_zero_and_all() -> None:
    ci_zero = wilson_interval(0, 25)
    assert ci_zero is not None
    assert ci_zero[0] == 0.0
    assert ci_zero[1] > 0.0
    ci_all = wilson_interval(25, 25)
    assert ci_all is not None
    assert ci_all[1] == 1.0
    assert ci_all[0] < 1.0


def test_high_confidence_errors_only_wrong_conclusive() -> None:
    records = [
        _record(
            "a", "SCREEN_MOBILE", "LIVE", "single-quality-v1", confidence=0.95
        ),  # wrong, high conf
        _record("b", "LIVE", "LIVE", "single-quality-v1", confidence=0.95),  # correct
        _record(
            "c", "SCREEN_MOBILE", "UNCERTAIN", "single-quality-v1", confidence=0.95
        ),  # uncertain
        _record(
            "d", "SCREEN_MOBILE", "PRINT_ATTACK", "single-quality-v1", confidence=0.6
        ),  # wrong low conf
        _record(
            "e",
            "SCREEN_MOBILE",
            None,
            "single-quality-v1",
            error="PROVIDER_TIMEOUT",
            confidence=0.95,
        ),
    ]
    errors = high_confidence_errors(records)
    assert [e["sample_id"] for e in errors] == ["a"]


def test_provider_reliability_separates_errors() -> None:
    records = [
        _record("a", "LIVE", "LIVE", "single-quality-v1"),
        _record("b", "LIVE", None, "single-quality-v1", error="PROVIDER_TIMEOUT"),
        _record("c", "LIVE", None, "single-quality-v1", error="PROVIDER_RATE_LIMITED"),
    ]
    reliability = provider_reliability(records)
    assert reliability["successful_requests"] == 1
    assert reliability["timeouts"] == 1
    assert reliability["rate_limited"] == 1


def test_paired_strategy_comparison() -> None:
    records = [
        _record("a", "SCREEN_MOBILE", "LIVE", "single-quality-v1"),  # wrong
        _record(
            "a", "SCREEN_MOBILE", "SCREEN_REPLAY", "temporal-triad-v1"
        ),  # correct -> triad fixes
        _record("b", "LIVE", "LIVE", "single-quality-v1"),  # both correct
        _record("b", "LIVE", "LIVE", "temporal-triad-v1"),
        _record("c", "PRINT_PHOTO", "LIVE", "single-quality-v1"),  # wrong -> spoof->LIVE single
        _record("c", "PRINT_PHOTO", "PRINT_ATTACK", "temporal-triad-v1"),
    ]
    comparison = paired_strategy_comparison(records)
    assert comparison["counts"]["single_wrong_triad_correct"] == 2
    assert comparison["counts"]["both_correct"] == 1
    assert comparison["paired_spoof_to_live"]["single"] == 2
    assert comparison["paired_spoof_to_live"]["triad"] == 0


def test_validate_run_flags_guards() -> None:
    assert validate_run_flags("mock", False, None, 5) is None
    assert "live" in (validate_run_flags("gemini", False, None, 5) or "").lower()
    assert "--max-requests" in (validate_run_flags("gemini", True, None, 5) or "")
    assert "exceeds" in (validate_run_flags("gemini", True, 3, 5) or "")
    assert validate_run_flags("gemini", True, 10, 5) is None


def test_screen_display_maps_to_screen_replay() -> None:
    correct = _record("s", "SCREEN_DISPLAY", "SCREEN_REPLAY", "single-quality-v1")
    wrong = _record("s", "SCREEN_DISPLAY", "LIVE", "single-quality-v1")
    from app.experiments.vlm.metrics import is_correct

    assert is_correct(correct) is True
    assert is_correct(wrong) is False
