---
description: Run the complete LivePhoto regression suite (backend + frontend + E2E) and report results honestly using the livephoto-regression skill.
---

Run full LivePhoto verification.

1. Load and follow the `livephoto-regression` skill.
2. Run backend checks (`cd backend`: `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run mypy app`, `uv run pytest`).
3. Run frontend checks (`cd frontend`: `npm run lint`, `npm run format:check`,
   `npm run typecheck`, `npm run test:run`, `npm run build`, `npm run test:e2e`).
4. Run `git diff --check` and `git status`.
5. Inspect skipped tests: separate expected skips (real-model smoke, live-provider integration)
   from unexpected skips.
6. Report exact pass/fail/skip counts per suite and any failures verbatim.

Do not mark work COMPLETE if required tests are failing.