"""OpenTelemetry foundation (M0 OBSERVABILITY, M1 §47).

M1 does not configure a production OTLP collector. Telemetry is disableable via
``OTEL_ENABLED=false`` (default) and no exporter is configured unless explicitly requested
(``OTEL_TRACES_EXPORTER=console`` for local debugging). No tracing exporter may prevent the
application from starting locally.
"""

from __future__ import annotations

import time

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings


def init_otel(settings: Settings) -> trace.Tracer | None:
    """Initialize the OpenTelemetry SDK. Returns a tracer, or ``None`` when disabled."""
    if not settings.otel_enabled:
        return None

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.app_version,
        }
    )
    provider = TracerProvider(resource=resource)
    if settings.otel_traces_exporter == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(settings.otel_service_name)


class TracingMiddleware:
    """Wrap each HTTP request in a server span when OpenTelemetry is enabled.

    Disabled (no-op) when the tracer is ``None`` so it never blocks startup.
    """

    def __init__(self, app: ASGIApp, tracer: trace.Tracer | None) -> None:
        self.app = app
        self.tracer = tracer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.tracer is None:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        span = self.tracer.start_span(
            "http.request",
            kind=trace.SpanKind.SERVER,
            attributes={
                "http.request.method": scope.get("method", ""),
                "url.path": scope.get("path", ""),
            },
        )
        status: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            span.set_attribute("http.response.status_code", status or 500)
            span.set_attribute("http.request.duration_seconds", time.perf_counter() - start)
            span.end()
