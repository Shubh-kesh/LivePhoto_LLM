"""Persistence foundation (M0 ADR-006, M1 §30-34).

- Microsoft SQL Server is the production database; SQLAlchemy 2.0 is configured to be MSSQL
  compatible.
- M1 must NOT require a local SQL Server: the application boots with an empty ``DATABASE_URL`` and
  DB-dependent routes do not exist yet.
- Metadata (decisions, versions, audit, review) lives in MSSQL; biometric images live in object
  storage (later milestone). No Base64/biometric images in business tables.
- No business tables exist yet; Alembic is initialized and wired to settings.
"""

from app.db.base import Base
from app.db.engine import engine_from_settings
from app.db.session import create_session_factory

__all__ = ["Base", "create_session_factory", "engine_from_settings"]
