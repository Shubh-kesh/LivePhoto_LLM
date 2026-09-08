---
name: livephoto-regression
description: Use to run and assess the complete LivePhoto regression suite (backend ruff/format/mypy/pytest, frontend lint/format/type/test/build, Playwright E2E) and report pass/fail/skipped accurately. Triggers on "run tests", "regression", "verify", "all checks".
---

# LivePhoto Regression

Run and assess the complete LivePhoto regression. Report failures honestly; do not mark a milestone
COMPLETE if required tests fail.

## Steps

1. Discover the actual repo commands from `AGENTS.md` / `package.json` / `pyproject.toml` (do not
   assume).
2. Backend (run from `backend/`):
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run mypy app`
   - `uv run pytest`
3. Frontend (run from `frontend/`):
   - `npm run lint`
   - `npm run format:check`
   - `npm run typecheck`
   - `npm run test:run` (or `npm run test -- --run`)
   - `npm run build`
   - `npm run test:e2e`
4. Inspect skipped tests: distinguish **expected skips** (manual-only real-model smoke,
   `VLM_LIVE_TESTS_ENABLED`, `LIVEPHOTO_RUN_REAL_MODEL_SMOKE`) from **new/unexpected skips**.
5. Run `git diff --check` and inspect `git status`.

## Reporting

- State exact pass/fail/skip counts per suite.
- List any failures verbatim with file/line references — do not hide them.
- Call out unexpected skips.
- Note which suites were or were not run (e.g. E2E requires a Docker/backend dev server).
- If any required check fails, the milestone cannot be reported COMPLETE.