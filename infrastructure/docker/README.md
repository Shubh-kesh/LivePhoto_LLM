# LivePhoto — Container Images (M5.6)

This directory documents the Docker packaging for LivePhoto. It contains **images and tooling
only** — no Kubernetes manifests, Helm charts or Terraform. Deployment into GKE (or the office
Artifact Registry) is done manually by the user.

## Images

| Image | Dockerfile | Port | Health |
|---|---|---|---|
| `livephoto-backend` | `backend/Dockerfile` | 8000 | `/health/live`, `/health/ready` |
| `livephoto-frontend` | `frontend/Dockerfile` | 8080 | static (nginx) |
| `livephoto-mssql` (reference only) | official `mcr.microsoft.com/mssql/server` | 1433 | SQL Server |

See `IMAGE_INVENTORY.md` for the pinned inventory (base images, digests, versions, git SHA).

## Building (backend + frontend only)

```bash
./scripts/build-uat-images.sh --platform linux/amd64 --tag "$(git rev-parse --short HEAD)"
```

- Builds `livephoto-backend:<sha>` and `livephoto-frontend:<sha>`.
- Add `--platform linux/amd64` when targeting an amd64 GKE office environment from an Apple
  Silicon (arm64) Mac.
- No push. No Kubernetes.

## Running locally (reference commands)

Backend:
```bash
docker run --rm -p 8000:8000 \
  -e APP_ENV=uat \
  -e VLM_EXPERIMENT_ENABLED=true \
  -e VLM_UAT_LOCAL_EXPERIMENT_ENABLED=true \
  -e VLM_PROVIDER=local \
  -e LOCAL_VLM_BASE_URL=http://host.docker.internal:8000/v1 \
  -e LOCAL_VLM_MODEL=google/gemma-3-12b-it \
  livephoto-backend:<sha>
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

Frontend (with VLM test UI enabled, no rebuild):
```bash
docker run --rm -p 8080:8080 \
  -e LIVEPHOTO_APP_ENV=uat \
  -e LIVEPHOTO_API_BASE_URL=http://localhost:8000 \
  -e LIVEPHOTO_VLM_EXPERIMENT_UI_ENABLED=true \
  livephoto-frontend:<sha>
# then verify:
#   http://localhost:8080/
#   http://localhost:8080/capture   (direct refresh works — SPA fallback)
#   http://localhost:8080/runtime-config.js
```

The same frontend image can run once with `LIVEPHOTO_VLM_EXPERIMENT_UI_ENABLED=false` (default
customer UX, identical to M5.5) and again with `true` — no rebuild required (M5.6 §83).

## MSSQL (reference, not built by us)

Mirror the official image into the office Artifact Registry (see `IMAGE_INVENTORY.md`):
```bash
docker pull --platform linux/amd64 mcr.microsoft.com/mssql/server:2022-latest
docker tag mcr.microsoft.com/mssql/server:2022-latest <artifact-registry>/livephoto-mssql:2022
# user pushes manually
```

- `MSSQL_SA_PASSWORD`, `ACCEPT_EULA` and `DATABASE_URL` are **runtime deployment config**, never
  baked into the image (M5.6 §61-62).
- SQL Server Linux containers require supported **x86-64 Linux nodes**; the image may be mirrored
  from an ARM Mac but is not a supported local ARM SQL Server runtime (M5.6 §64).
- The LivePhoto app still starts without a database (M5.6 §62). No SQL init scripts are included —
  real persistence arrives in later milestones (M5.6 §63).

## Image security (M5.6 §81)

Inspect built images before deploy — they must NOT contain `.env`, API keys, datasets,
evaluation artifacts, camera files, git history, or build caches:

```bash
docker run --rm --entrypoint sh livephoto-backend:<sha> -c 'ls -la /app; find /app -name "*.env" -o -name "*.log"'
docker history livephoto-backend:<sha>
docker run --rm livephoto-backend:<sha> python -c "import os; print([k for k in ('GEMINI_API_KEY','GROQ_API_KEY','LOCAL_VLM_API_KEY','OPENROUTER_API_KEY') if os.environ.get(k)])"
```
