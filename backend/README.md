# LivePhoto Backend

FastAPI modular monolith for the LivePhoto passive liveness platform (M1 foundation).

## Package boundaries

```
app/
├── api/            HTTP only: routes, parsing, response mapping, DI (no business logic)
│   └── v1/         business routes under /api/v1 (currently: /info)
├── core/           cross-cutting infrastructure: config, logging, errors, middleware, health
├── db/             SQLAlchemy persistence foundation (engine/session/metadata)
├── domain/         business concepts independent of FastAPI/SQLAlchemy (enums, contracts)
├── services/       future application-use-case orchestration (empty in M1)
├── validators/     future liveness-validation seam (Protocol only in M1)
├── providers/
│   └── vision/     future VLM provider seam (no providers, no external calls in M1)
├── integrations/
│   └── bank/       future bank S2S + callback boundary (documented only in M1)
├── observability/  metrics (Prometheus) and tracing (OpenTelemetry) helpers
└── main.py         ASGI entry point: `app.main:app`
```

## Trust-model note (M0 ADR-003)

The browser is **untrusted**; the server is authoritative. Two API audiences are kept separate by
design and must never share credentials:

- **Bank Integration API** — future callers are the bank backend (mTLS / OAuth2 client
  credentials / signed requests; mechanism pending). The browser must never receive bank server
  credentials.
- **Capture API** — future callers are the customer browser holding only a short-lived, opaque,
  session-scoped capture credential. No capture endpoints exist in M1.

## Run locally

Requires Python 3.13 and `uv`.

```bash
cp ../.env.example .env     # optional local overrides
uv sync
uv run uvicorn app.main:app --reload
```

OpenAPI docs (local): http://localhost:8000/docs

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
uv run pytest --cov=app --cov-report=term-missing
```

## Concurrency model (documented)

FastAPI async endpoints handle I/O-bound work on the event loop. SQLAlchemy is configured as a
**sync** engine; DB-bound endpoints will be written as sync `def` (FastAPI runs them in the
threadpool) or use an async engine later if needed. Heavy CPU/GPU model inference must not block
the event loop; it moves to separate workers/inference services in later milestones
(`docs/NON_FUNCTIONAL_REQUIREMENTS.md`).

## Configuration

See `../.env.example`. All settings are validated by `app/core/config.py` (pydantic-settings).

## MSSQL note

Production persistence is Microsoft SQL Server. M1 does **not** require a local SQL Server:
the application boots with an empty `DATABASE_URL`. Alembic is initialized and wired to settings;
no business schema exists yet. See `docs/DEVELOPMENT_GUIDE.md` for the SQL Server development
options (remote/dev SQL Server, x86-64 host, approved cloud SQL Server).