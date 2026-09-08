"""Prometheus metrics foundation (M0 OBSERVABILITY, M1 §45-46).

Cardinality rules:
- Labels are low cardinality: ``method``, route template ``path`` (or ``unmatched``), ``status``.
- No customer/session/transaction IDs, account numbers, or URL tokens as labels.

Production ``/metrics`` must not be publicly internet accessible; it is scraped by Prometheus over
internal access. Local M1 exposure is acceptable and documented.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response

http_requests_total = Counter(
    "livephoto_http_requests_total",
    "Total HTTP requests handled",
    labelnames=("method", "path", "status"),
)

http_request_duration_seconds = Histogram(
    "livephoto_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# VLM experiment metrics (M4 §125-126). Low cardinality only: provider, coarse result/error —
# never transaction/capture/sample IDs or model-generated text.
vlm_requests_total = Counter(
    "livephoto_vlm_requests_total",
    "Total VLM evaluation requests",
    labelnames=("provider", "result"),
)

vlm_request_duration_seconds = Histogram(
    "livephoto_vlm_request_duration_seconds",
    "VLM evaluation duration in seconds",
    labelnames=("provider",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

vlm_provider_errors_total = Counter(
    "livephoto_vlm_provider_errors_total",
    "VLM provider errors",
    labelnames=("provider", "error_type"),
)

# M5.8 — Secure Consumer Integration. Low-cardinality only: consumer is bounded by configured
# profiles; never transaction/session/token/attempt IDs or reason text as labels.
launch_sessions_total = Counter(
    "livephoto_launch_sessions_total",
    "Consumer launch sessions requested",
    labelnames=("consumer", "result"),
)

redemptions_total = Counter(
    "livephoto_launch_redemptions_total",
    "Launch token redemptions",
    labelnames=("result",),
)

browser_capture_attempts_total = Counter(
    "livephoto_browser_capture_attempts_total",
    "Registered browser capture attempts",
    labelnames=("consumer",),
)

submit_total = Counter(
    "livephoto_submit_total",
    "Browser submit attempts",
    labelnames=("result",),
)

callback_events_total = Counter(
    "livephoto_callback_events_total",
    "Consumer callback delivery events",
    labelnames=("consumer", "result"),
)

callback_duration_seconds = Histogram(
    "livephoto_callback_duration_seconds",
    "Consumer callback duration in seconds",
    labelnames=("consumer",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

status_reads_total = Counter(
    "livephoto_status_reads_total",
    "Consumer status API reads",
    labelnames=("consumer",),
)


def record_launch_session(consumer: str, result: str) -> None:
    launch_sessions_total.labels(consumer, result).inc()


def record_redemption(result: str) -> None:
    redemptions_total.labels(result).inc()


def record_capture_attempt(consumer: str) -> None:
    browser_capture_attempts_total.labels(consumer).inc()


def record_submit(result: str) -> None:
    submit_total.labels(result).inc()


def record_callback(consumer: str, result: str, duration_seconds: float) -> None:
    callback_events_total.labels(consumer, result).inc()
    callback_duration_seconds.labels(consumer).observe(duration_seconds)


def record_status_read(consumer: str) -> None:
    status_reads_total.labels(consumer).inc()


def record_vlm_evaluation(
    provider: str,
    result: str,
    duration_seconds: float,
    error_type: str | None = None,
) -> None:
    vlm_requests_total.labels(provider, result).inc()
    vlm_request_duration_seconds.labels(provider).observe(duration_seconds)
    if error_type is not None:
        vlm_provider_errors_total.labels(provider, error_type).inc()


def record_http_request(
    method: str, route_path: str | None, status: int, duration_seconds: float
) -> None:
    path = route_path or "unmatched"
    http_requests_total.labels(method, path, str(status)).inc()
    http_request_duration_seconds.labels(method, path).observe(duration_seconds)


def metrics_response(_request: Request) -> Response:
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
