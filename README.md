# LivePhoto

**Banking-grade passive liveness and presentation-attack detection.**

LivePhoto answers one question: *is the photograph being captured from a real human physically
present in front of the camera at capture time?* It is a liveness/PAD component, **not** an
identity-matching system.

> **Do not add real banking customer images or confidential datasets to this repository.** See
> `SECURITY.md` and `docs/DATA_GOVERNANCE.md`.

## Status

- **M0 COMPLETE** — product specification, threat model, architecture baseline (`docs/`).
- **M1 COMPLETE** — repository & engineering foundation (this milestone).
- M2+ (camera capture, liveness, models, deployment) are planned in `docs/ROADMAP.md` and are
  **not** implemented yet.

## Architecture summary

- Browser-based passive capture (burst frames), **server-authoritative** decision (M0 ADR-003).
- Defence-in-depth validator pipeline; validators produce evidence, a policy engine decides
  `PASS / RETRY / REVIEW / FAIL` (M0 ADR-004).
- **Modular monolith** first (M0 P14); inference may be extracted later if measurements justify.
- MSSQL for metadata/decisions/versions; private object storage for biometric images
  (M0 ADR-006).
- External VLM providers are **POC-only**; production targets a self-hosted model
  (M0 ADR-005).
- React SPA (M0 ADR-007) + FastAPI backend (M0 ADR-008); GCP/GKE + HPA production direction
  (M0 ADR-009).

See `docs/SYSTEM_CONTEXT.md` for diagrams and trust boundaries, and `docs/adr/` for decisions.

## Repository structure

```
livephoto/
├── backend/          FastAPI modular monolith (Python 3.13, uv)
├── frontend/         React + TypeScript + Vite SPA
├── ml/               model research/evaluation (not production inference)
├── infrastructure/   docker/kubernetes/terraform/monitoring (future milestones)
├── scripts/          developer helper scripts
├── docs/             M0 architecture baseline + DEVELOPMENT_GUIDE.md
├── .github/workflows CI
├── .editorconfig
├── .env.example
└── SECURITY.md
```

## Prerequisites

- Python 3.13.x and [`uv`](https://docs.astral.sh/uv/)
- Node.js 24 LTS (>= 22.12) and npm
- Git

## Quick start

### Backend

```bash
cd backend
cp ../.env.example .env   # optional local overrides
uv sync
uv run uvicorn app.main:app --reload
```

- Health: http://localhost:8000/health/live , http://localhost:8000/health/ready
- Info: http://localhost:8000/api/v1/info
- OpenAPI docs (local): http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173 . The foundation page shows application info fetched from the backend.

## How to test / lint / type-check

```bash
# backend (from backend/)
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest                       # with coverage: uv run pytest --cov=app

# frontend (from frontend/)
npm run lint
npm run format:check
npm run typecheck
npm run test:run
npm run build
```

Full developer guidance: `docs/DEVELOPMENT_GUIDE.md`.

## Environment configuration

Safe placeholders live in `.env.example`. Copy to `backend/.env` for local overrides. Never
commit `.env` files or real credentials.

## MSSQL development note

Production persistence is Microsoft SQL Server. **M1 does not require a local SQL Server** — the
application boots with an empty `DATABASE_URL` and only foundation endpoints exist. Supported
development approaches (later milestones): remote/dev SQL Server, bank-managed dev SQL Server,
x86-64 development host, or an approved cloud SQL Server. See `docs/DEVELOPMENT_GUIDE.md`.

## Roadmap & documentation

- `docs/ROADMAP.md` — milestones M0–M23
- `docs/PRODUCT_REQUIREMENTS.md` — product scope and decision semantics
- `docs/THREAT_MODEL.md` — threat model
- `docs/DEVELOPMENT_GUIDE.md` — development conventions