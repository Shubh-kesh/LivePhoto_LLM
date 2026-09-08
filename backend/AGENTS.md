# LivePhoto Backend — Engineering Guidance

Durable backend rules for OpenCode agents. See the repository-root `AGENTS.md` for LivePhoto-wide
rules; this file adds backend-specific invariants.

## Architecture

- **FastAPI routes remain thin.** Business logic lives in `app/services/`, `app/domain/`, and
  feature modules (`app/experiments/`, `app/portrait/`, `app/transactions/`, `app/providers/`).
- HTTP routers (`app/api/`) validate input and delegate; do not put decision logic in routes.
- **Strict Pydantic schemas** at every trust boundary; prefer `extra="forbid"` on external-input
  models. Validate all external input (multipart files, form fields, headers, request bodies).
- Keep workflow state separate from model/decision results. Model outputs are evidence, not
  authorization.

## Filesystem / transactions

- Storage is filesystem-backed (`FILE_STORAGE_ROOT`); never introduce object storage unless
  explicitly requested.
- Never construct filesystem paths from untrusted input. Preserve root-confinement and symlink
  protections; use `app/transactions/` safe-path helpers.
- Use atomic filesystem writes (temp file → fsync → atomic rename) for metadata.
- Refer to artifacts with transaction-relative references; never expose absolute server paths to
  the frontend.

## Security & privacy

- Never log image bytes, Base64, data URLs, Authorization headers, API keys, or `.env` contents.
  Use the structured-logging redaction layer (`app/core/logging.py`).
- Use typed application errors (e.g., `ApiError`, provider/transaction/portrait error types);
  map them to safe customer messages at the edge.
- Preserve structured logging (structlog, JSON in production); keep Prometheus labels
  low-cardinality.
- **Do not use model confidence directly as an authorization decision.**
- External callbacks require an explicit timeout; external HTTP redirects must not be followed
  unless explicitly designed.

## Configuration

- New configuration belongs in the central `Settings` class (`app/core/config.py`), with
  validation (field validators) for constrained values.
- Keep `.env.example` and documentation synchronized. When `.env.example` changes, the completion
  report MUST include the `LOCAL .ENV ACTION REQUIRED` section with exact values.
- Test-only behavior must be impossible in UAT/production (build-time or env-gated seams, never
  trust-the-client).

## Testing

Discovered commands (run from `backend/`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

- Update the lockfile when dependencies change: `uv lock && uv sync`.
- Tests use explicit settings (`Settings(_env_file=None, ...)`) and temp storage roots; they must
  not depend on `.env`, the network, or MSSQL.