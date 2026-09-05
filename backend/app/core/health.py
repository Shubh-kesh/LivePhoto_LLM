"""Health-check machinery.

``/health/live`` answers "is the process alive" and must not fail because a dependency is down.
``/health/ready`` answers "can this instance serve requests" and runs registered readiness checks
(e.g. the database) that are added later; M1 registers a database check only when a ``DATABASE_URL``
is configured, so the application boots fine without MSSQL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, text


class ReadinessResult(BaseModel):
    name: str
    status: Literal["ok", "unavailable"]
    detail: str | None = None


ReadinessCheck = Callable[[], ReadinessResult]


def database_readiness_check(engine: Engine) -> ReadinessResult:
    """Ping the configured database. Safe: does not expose credentials or configuration."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return ReadinessResult(name="database", status="unavailable", detail="database unreachable")
    return ReadinessResult(name="database", status="ok")
