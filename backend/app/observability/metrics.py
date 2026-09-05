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
