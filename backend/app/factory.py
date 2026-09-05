"""FastAPI application factory (M0 P14, M1 §14-15).

``create_app(settings)`` builds a fully configured application with no import-time side effects and
no external connections during import. Initialization/shutdown happen in the lifespan handler so
database pools, telemetry and model providers can be added later without executing at import time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import v1_router
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.health import database_readiness_check
from app.core.middleware import (
    MetricsMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.engine import engine_from_settings
from app.observability.metrics import metrics_response
from app.observability.otel import TracingMiddleware, init_otel


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: configure logging, optional engine, readiness checks.

    No external connections are made at import time or during startup; the engine (if any) is
    created lazily and only connects on first use.
    """
    settings: Settings = app.state.settings

    from app.core.logging import configure_logging

    configure_logging(settings)
    app.state.engine = engine_from_settings(settings.database_url)
    app.state.ready_checks = []
    if app.state.engine is not None:
        app.state.ready_checks.append(lambda: database_readiness_check(app.state.engine))
    yield
    if app.state.engine is not None:
        app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=_lifespan,
    )
    app.state.settings = settings

    register_exception_handlers(app)

    # Middleware order: outermost to innermost = CORS, RequestID, RequestLogging,
    # SecurityHeaders, Metrics, Tracing. Starlette wraps middleware in reverse add order, so we
    # add innermost first and outermost last.
    app.add_middleware(TracingMiddleware, tracer=init_otel(settings))
    if settings.prometheus_enabled:
        app.add_middleware(MetricsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.include_router(health_router)
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    if settings.prometheus_enabled:
        app.add_route(
            settings.metrics_path,
            metrics_response,
            methods=["GET"],
            include_in_schema=False,
        )

    return app
