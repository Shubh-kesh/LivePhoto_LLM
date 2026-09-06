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
