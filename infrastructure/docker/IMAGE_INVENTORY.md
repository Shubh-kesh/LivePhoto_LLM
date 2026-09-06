# LivePhoto — Image Inventory (M5.6 §60, §80)

Pinned inventory for the LivePhoto container images and the MSSQL reference. Fill in the
environment-specific values (Artifact Registry repo, git SHA, actual digests) when preparing a
real UAT deploy. No secrets/hostnames are committed here.

## LivePhoto application images

| Service | Local image | Base image | Platform | App version | Git SHA | Runtime port | Health endpoint | Notes |
|---|---|---|---|---|---|---|---|---|
| backend | `livephoto-backend:<sha>` | `python:3.13-slim` (runtime) | linux/amd64 (target) | 0.1.0 | `<git rev-parse --short HEAD>` | 8000 | `/health/live`, `/health/ready` | non-root `appuser`; uv-frozen deps; no dev deps |
| frontend | `livephoto-frontend:<sha>` | build `node:24-alpine` → runtime `nginx:1.27-alpine` | linux/amd64 (target) | 0.1.0 | `<git rev-parse --short HEAD>` | 8080 | static | non-root `appuser`; SPA fallback; runtime-config.js generated from env |

## MSSQL reference (mirrored from official Microsoft image)

| Service | Image source | Pinned tag | SQL Server version | Base digest (fill after pull) | Platform | Port | Notes |
|---|---|---|---|---|---|---|---|
| mssql | `mcr.microsoft.com/mssql/server` | `2022-latest` (resolve + pin a digest) | SQL Server 2022 | `<docker image inspect --format '{{index .RepoDigests 0}}' ...>` | linux/amd64 (x86-64 only) | 1433 | mirrored into office Artifact Registry; runtime config only |

Resolve and pin the digest (do not rely on the mutable `latest` forever):
```bash
docker pull --platform linux/amd64 mcr.microsoft.com/mssql/server:2022-latest
docker image inspect --format '{{index .RepoDigests 0}}' mcr.microsoft.com/mssql/server:2022-latest
# record the digest here, then:
docker tag mcr.microsoft.com/mssql/server:2022-latest <artifact-registry>/livephoto-mssql:2022-<digest-short>
```

## Artifact Registry tags (fill in)

- Artifact Registry repo: `<project>/<region>/<repo>` (office Artifact Registry hostname/project to be supplied)
- Backend: `<artifact-registry>/livephoto-backend:<sha>` (convenience: `:uat`)
- Frontend: `<artifact-registry>/livephoto-frontend:<sha>` (convenience: `:uat`)
- MSSQL: `<artifact-registry>/livephoto-mssql:2022-<digest-short>`

## Platform / architecture

- Office UAT target: **linux/amd64** (GKE x86-64 nodes).
- Build from an Apple Silicon (arm64) Mac with `docker buildx build --platform linux/amd64 …`
  (see `scripts/build-uat-images.sh`).
- SQL Server Linux container requires supported x86-64 Linux nodes (M5.6 §64).

## Environment inputs still required for a real UAT deploy (M5.6 §96)

- Office Artifact Registry hostname/project/repository
- UAT API hostname (`LIVEPHOTO_API_BASE_URL`)
- GKE node architecture / image pull secrets
- Gemma serving endpoint (`LOCAL_VLM_BASE_URL`) + exact model (`LOCAL_VLM_MODEL`)
- GPU type / VRAM for the Gemma inference service
- Gemma API authentication method
- MSSQL runtime password / license configuration
