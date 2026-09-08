# LivePhoto — Repository Engineering Guidance

Durable, LivePhoto-wide engineering instructions for OpenCode agents. These rules are stable and
milestone-independent; temporary task details belong in the user prompt, not here.

## What LivePhoto is

- Banking-oriented face-photo capture / passive-liveness platform (monorepo).
- **Backend:** Python 3.13 / FastAPI (`backend/`).
- **Frontend:** React / TypeScript / Vite (`frontend/`).
- **Milestones:** M0–M5.x complete; M6+ (accuracy-driven spoof detection) is planned but **not**
  implemented. Do not begin a later milestone opportunistically.

## Architecture invariants

- **Server-authoritative decisions.** Browser quality checks (face, exposure, eye state) are
  preliminary UX/evidence signals, never authoritative PASS/LIVE. Do not let browser-controlled
  state authorize security-sensitive decisions.
- Keep workflow state separate from model/decision results.
- Backend routes stay thin; logic lives in services/domain modules. Strict Pydantic schemas at
  trust boundaries.

## File storage

- Artifact storage is **filesystem-backed**:
  - local = local filesystem (`FILE_STORAGE_ROOT`),
  - UAT/production = mounted enterprise filesystem volume.
- **Do NOT introduce GCS/S3/Azure Blob/object storage unless explicitly requested.**
- Artifacts live under internal transaction folders
  (`<root>/transactions/<transaction_id>/`) and are referenced by safe, transaction-relative
  artifact references. **Never expose absolute server filesystem paths to the frontend.**

## Transactions

- Keep external consuming-application transaction IDs distinct from LivePhoto internal
  filesystem-safe transaction IDs. Never use untrusted external IDs directly as filesystem paths.

## Security

Never log or commit: API keys, JWTs, Authorization headers, cookies, launch tokens,
browser-session tokens, CSRF tokens, callback credentials, Base64 image payloads, real customer
images, `.env` contents, or internal service URLs.

Never introduce security bypasses (`force_pass`, `skip_verification`, `trust_client`, …) unless
explicitly test-only and impossible in UAT/production. Preserve root-confinement and symlink
protections for all filesystem access.

## Environment variables

- If `.env.example` changes, the completion report MUST include an explicit section:

  ```text
  LOCAL .ENV ACTION REQUIRED
  ```

  listing the exact variables/values the developer must add or update in their real `.env`.
- Never claim `.env` was modified unless it actually was. Do not automatically edit real `.env`
  files. Never print secret values.

## Testing

Before milestone completion, run the repository's actual checks. Discovered commands:

Backend (`cd backend`):
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy app`
- `uv run pytest`
- Lockfile sync when dependencies change: `uv lock && uv sync`

Frontend (`cd frontend`):
- `npm ci` (when lockfile changes)
- `npm run lint`
- `npm run format:check`
- `npm run typecheck`
- `npm run test:run` (or `npm run test -- --run`)
- `npm run build`
- `npm run test:e2e`

## Git

Never `git push`, force-push, rewrite history, commit secrets, or commit runtime artifacts without
explicit instruction. Before committing: `git status`, `git diff --check`, `git diff`. Stage only
intended files; never stage `.env`, model weights, captures, or test media.

## Milestone discipline

- Complete only the requested milestone.
- Explicitly report unresolved limitations.
- Do not call engineering-complete work accuracy-validated without evidence.
- Do not make spoof/liveness accuracy claims from mock/synthetic tests.
- Keep an evidence-based completion report distinguishing:
  `implemented`, `tested`, `manually verified`, `not tested`, `known limitation`.