"""Observability: Prometheus metrics and OpenTelemetry hooks.

Kept out of domain code (M0 P8, OBSERVABILITY_STRATEGY). No PII/biometrics/customer IDs in metric
labels; labels are low cardinality (method, route template, status).
"""

from app.observability.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    metrics_response,
    record_http_request,
)
from app.observability.otel import init_otel

__all__ = [
    "http_request_duration_seconds",
    "http_requests_total",
    "init_otel",
    "metrics_response",
    "record_http_request",
]
