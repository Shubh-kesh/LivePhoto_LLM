# LivePhoto — Development Guide

Status: M1. Conventions for contributing to the LivePhoto repository. Architecture constraints are
in `docs/ARCHITECTURE_PRINCIPLES.md` and the ADRs; this guide is about *how* to develop here.

---

## 1. Tool versions

| Tool | Version | Notes |
|---|---|---|
| Python | `>=3.13,<3.14` | standard CPython; no free-threaded builds |
| uv | recent | backend dependency & venv management |
| Node.js | 24 LTS (engines `>=22.12.0`) | npm only (no pnpm/yarn/bun) |
| npm | 10+ | lockfile: `package-lock.json` |
| Git | any recent | default branch `main` |

## 2. Repository layout

```
backend/          FastAPI modular monolith (see backend/README.md)
frontend/         React + TS + Vite SPA (see frontend/README.md)
ml/               research/evaluation only — never production inference, never biometric data
infrastructure/   docker/kubernetes/terraform/monitoring placeholders (M16+)
scripts/          developer helper scripts
docs/             M0 architecture baseline + this guide
```

## 3. Dependency management

- **Backend:** `uv`; edit `pyproject.toml`, then `uv lock && uv sync`. Commit `uv.lock`.
  Add only dependencies a milestone actually needs (no ML/AI SDKs before their milestone).
- **Frontend:** `npm`; edit `package.json`, then `npm install`. Commit `package-lock.json`.
- Never depend on floating versions without a lockfile; never commit `.venv` or `node_modules`.

## 4. Branching guidance

- `main` is the integration branch. Feature branches + pull requests for non-trivial work.
- CI runs on every PR and push to `main` (`.github/workflows/`).

## 5. Testing conventions

- **Backend (pytest):** unit tests in `backend/tests/unit/`, contract tests in
  `backend/tests/contract/`, DB-touching integration tests (later) in `backend/tests/integration/`.
  Unit tests must require **no external network and no MSSQL**. DB integration tests use
  `TEST_DATABASE_URL` and are skipped with a clear reason when no integration database exists.
- **Frontend (Vitest + Testing Library + jsdom):** tests live next to what they test under
  `src/test/`. No camera mocking in M1.
- Coverage floor: backend `>= 80%` (`pyproject.toml` `[tool.coverage.report] fail_under`).

## 6. Linting / formatting / type checking

- **Backend:** Ruff for lint + format + import sort; mypy (strict) for types.
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`
  - Fix format with `uv run ruff format .`
- **Frontend:** ESLint + Prettier; `tsc --noEmit` for types.
  - `npm run lint`, `npm run format:check`, `npm run typecheck`
  - Fix format with `npm run format`

## 7. Logging rules

- Structured logging only (`app/core/logging.py`). `LOG_FORMAT=json` in production, `console`
  locally.
- **Never log:** biometric image bytes, Base64 images, access tokens, authorization headers,
  cookies, API keys, passwords, raw session secrets, PII.
- Every request has a `request_id` (header `X-Request-ID`) bound into log context.
  `request_id`, `correlation_id` (bank transaction), and `session_id` are distinct concepts.
- Use the redaction processor (`redact_processor`) as the safety net; never log header values by
  default (`safe_headers` exists for the rare allowed case).

## 8. Configuration

- All settings live in `backend/app/core/config.py` (pydantic-settings), sourced from env vars and
  an optional local `.env` (copy from root `.env.example`).
- Environment name (`APP_ENV`) is **not** a security authorization mechanism; security properties
  are explicit settings.
- CORS origins are a JSON list (`CORS_ORIGINS=["http://localhost:5173"]`); wildcard is rejected
  when credentials are enabled.
- Add a setting only when a milestone needs it; do not pre-add dozens of unused knobs.

## 9. Database integration testing (later milestones)

- Production DB is MSSQL. M1 does not require a local SQL Server. Supported development approaches:
  remote/dev SQL Server, bank-managed dev SQL Server, x86-64 development host, or an approved cloud
  SQL Server.
- SQLite is **not** production-equivalent and must not be presented as such; it may appear only in
  isolated unit tests to exercise code paths that need a real engine.
- Migrations: `cd backend && uv run alembic revision --autogenerate -m "..."`, always reviewed by
  hand; run with `uv run alembic upgrade head` against a configured `DATABASE_URL`.

## 10. Security rules

- The browser is untrusted; the server is authoritative. Client-side checks are UX only.
- Bank integration APIs and the browser capture flow are separate trust models; browser clients
  never receive bank server credentials.
- No secrets, keys, certificates, `.env` files, biometric images, or customer datasets in the
  repository (`.gitignore`, `SECURITY.md`).
- New endpoints return the standard error envelope; never leak stack traces or internal config.
- Security headers are applied centrally (`app/core/middleware.py`); do not bypass them.

## 11. How to add a new backend module

1. Place code by responsibility: `api/` (HTTP only), `services/` (orchestration), `domain/`
   (business concepts, no FastAPI/SQLAlchemy imports), `validators/`, `providers/`,
   `integrations/`, `db/`, `observability/`, `core/`.
2. Add settings to `core/config.py` only if needed.
3. Wire the route in the application factory (`app/factory.py`).
4. Add tests (unit at minimum) and run: `ruff check`, `ruff format --check`, `mypy app`, `pytest`.
5. Add/update an ADR only for a genuinely settled architectural decision.

## 12. How to add a new frontend feature

1. Place code by feature: `features/<name>/` for feature-specific logic; shared transport in
   `api/`, schemas in `schemas/`, hooks in `hooks/`.
2. Define the Zod schema (mirroring the backend Pydantic contract) and infer the TS type from it;
   do not hand-duplicate the type.
3. Add a route in `app/App.tsx` and a page in `pages/`.
4. Add tests in `src/test/`.
5. Run: `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm run test:run`,
   `npm run build`.

## 13. Session-state contract (M1)

`backend/app/domain/session.py` defines `SessionState` (lifecycle) separate from
`DecisionOutcome` (liveness decision). Conceptual transitions (implemented in a later milestone):

```
CREATED -> ACTIVE -> CAPTURE_IN_PROGRESS -> VALIDATING -> PASS | RETRY -> ACTIVE | REVIEW | FAIL
CREATED/ACTIVE -> EXPIRED | CANCELLED
```

Terminal vs non-terminal classification is enforced in the domain module; arbitrary string status
values are not permitted.