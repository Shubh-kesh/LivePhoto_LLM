# Backend container image (M5.6 §47-50, §55-56, §65-66, §81).
#
# - Python 3.13, uv-lockfile-driven frozen install.
# - No dev/test dependencies in the final runtime.
# - Non-root runtime user; no .env, datasets, evaluation artifacts or API keys baked in.
# - Port 8000; production uvicorn command with graceful SIGTERM.
# Build (from repo root):
#   docker build -f backend/Dockerfile -t livephoto-backend:<sha> backend

# ---- build stage ----
FROM python:3.13-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/
WORKDIR /app
# Copy the project + lockfile and the package source so `uv sync --frozen` can install the app.
COPY pyproject.toml uv.lock ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-install-project

# ---- runtime stage ----
FROM python:3.13-slim
RUN groupadd --system appgroup && useradd --system --no-create-home --gid appgroup appuser
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app ./app
# No .env, no datasets, no evaluation artifacts, no credentials — never COPY them.
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
