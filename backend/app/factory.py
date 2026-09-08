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
from app.api.experiments_router import experiments_router
from app.api.health import router as health_router
from app.api.transactions_router import transactions_router
from app.api.xbiz import router as xbiz_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.health import ReadinessResult, database_readiness_check
from app.core.middleware import (
    MetricsMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.engine import engine_from_settings
from app.integrations import (
    ConsumerConfigError,
    ConsumerRegistry,
    IntegrationIndexStore,
    load_consumer_profiles,
)
from app.observability.metrics import metrics_response
from app.observability.otel import TracingMiddleware, init_otel
from app.transactions import TransactionFileStore


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: configure logging, storage, optional engine, readiness checks.

    No external connections are made at import time. The transaction store is filesystem-backed and
    initialized lazily; a storage failure does not prevent boot (the readiness check surfaces it).
    """
    settings: Settings = app.state.settings

    from app.core.logging import configure_logging

    configure_logging(settings)
    app.state.transaction_store = TransactionFileStore(
        settings.file_storage_root, settings.file_storage_transactions_dir
    )
    app.state.integration_index_store = IntegrationIndexStore(settings.file_storage_root)
    app.state.integration_index_store.initialize()
    if settings.portrait_segmentation_provider == "fake" and settings.app_env != "production":
        from app.portrait import FakePortraitSegmentation

        app.state.portrait_segmentation = FakePortraitSegmentation()
    app.state.engine = engine_from_settings(settings.database_url)
    app.state.ready_checks = []
    if app.state.engine is not None:
        app.state.ready_checks.append(lambda: database_readiness_check(app.state.engine))
    app.state.ready_checks.append(lambda: storage_readiness_check(app.state.transaction_store))

    # Consumer integration readiness: UAT/production require a valid consumer profile (fail closed);
    # local/test/dev may run without one (reported as integration_unavailable but not fatal).
    try:
        profiles = load_consumer_profiles(settings.consumer_profiles_path, settings.app_env)
        app.state.consumer_registry = ConsumerRegistry(profiles)
        app.state.consumer_registry_ok = True
    except ConsumerConfigError as exc:
        app.state.consumer_registry = ConsumerRegistry([])
        app.state.consumer_registry_ok = False
        app.state.consumer_config_error = str(exc)
    app.state.ready_checks.append(lambda: integration_readiness_check(app))

    yield
    if app.state.engine is not None:
        app.state.engine.dispose()


def storage_readiness_check(store: TransactionFileStore) -> ReadinessResult:
    health = store.check_health()
    return ReadinessResult(
        name="file_storage",
        status="ok" if health.ok else "unavailable",
        detail=health.detail,
    )


def integration_readiness_check(app: FastAPI) -> ReadinessResult:
    """Consumer-integration readiness.

    UAT/production require a valid consumer profile and fail closed. local/test/dev treat
    integration as optional and never fail base readiness on its absence (M5.8 §26).
    """
    settings = app.state.settings
    ok = bool(getattr(app.state, "consumer_registry_ok", False))
    if settings.app_env in ("uat", "production"):
        if not ok:
            return ReadinessResult(
                name="integration",
                status="unavailable",
                detail="consumer integration is not configured",
            )
        return ReadinessResult(name="integration", status="ok")
    return ReadinessResult(
        name="integration", status="ok", detail="configured" if ok else "optional"
    )


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
    app.include_router(experiments_router, prefix=settings.api_v1_prefix)
    app.include_router(transactions_router, prefix=settings.api_v1_prefix)
    app.include_router(xbiz_router)
    from app.api.v1.browser import router as browser_router
    from app.api.v1.integration import router as integration_router

    app.include_router(integration_router, prefix=settings.api_v1_prefix)
    app.include_router(browser_router, prefix=settings.api_v1_prefix)

    # Test-only canonical decision writer: strictly local/test/development + explicit flag.
    if (
        settings.app_env in ("local", "test", "development")
        and settings.decision_test_writer_enabled
    ):
        from app.api.v1.dev import router as dev_router

        app.include_router(dev_router, prefix=settings.api_v1_prefix)

    if settings.prometheus_enabled:
        app.add_route(
            settings.metrics_path,
            metrics_response,
            methods=["GET"],
            include_in_schema=False,
        )

    return app
