"""Database engine construction (M1 §31-32).

The engine/session lifecycle is isolated behind ``app/db``; routers must never create sessions
manually. Engines are created lazily and only when a ``DATABASE_URL`` is configured; no connection
is made at import time or at application startup.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine


def create_db_engine(database_url: str, **kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine without connecting (MSSQL-compatible by default)."""
    options: dict[str, Any] = {"pool_pre_ping": True}
    options.update(kwargs)
    return create_engine(database_url, **options)


def engine_from_settings(database_url: str) -> Engine | None:
    """Return an engine only if a database URL is configured, else ``None``.

    Returning ``None`` lets the foundation boot without MSSQL. Later milestones that require the
    database will pass an explicit URL.
    """
    if not database_url:
        return None
    return create_db_engine(database_url)
