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
def settings(tmp_path) -> Settings:
    # Tests never write into the real local-data tree: storage root is a temp directory.
    return make_settings(file_storage_root=str(tmp_path / "file-storage"))


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> StarletteTestClient:
    with TestClient(app) as test_client:
        yield test_client
