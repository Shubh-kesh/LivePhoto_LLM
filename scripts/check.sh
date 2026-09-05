#!/usr/bin/env bash
# LivePhoto developer helper scripts.
#
# Each script runs the given check for its component from the repository root.
# Portable POSIX-ish bash; no Make required.

set -euo pipefail

COMPONENT="${1:-all}"

run_backend() {
  echo "==> backend"
  (cd backend && uv sync --quiet && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest)
}

run_frontend() {
  echo "==> frontend"
  (cd frontend && npm ci --silent && npm run lint && npm run format:check && npm run typecheck && npm run test:run && npm run build)
}

case "$COMPONENT" in
  backend) run_backend ;;
  frontend) run_frontend ;;
  all)
    run_backend
    run_frontend
    ;;
  *)
    echo "usage: $0 [backend|frontend|all]" >&2
    exit 2
    ;;
esac

echo "==> all checks passed"