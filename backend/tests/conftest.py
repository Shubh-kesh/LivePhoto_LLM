"""Shared test fixtures.

All settings are passed explicitly so tests never depend on ``.env`` files or the developer's
shell environment. Tests require no external network and no database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient

from app.core.config import Settings
from app.factory import create_app


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "app_env": "test",
        "database_url": "",
        "prometheus_enabled": True,
        "otel_enabled": False,
        "log_format": "console",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> StarletteTestClient:
    with TestClient(app) as test_client:
        yield test_client
