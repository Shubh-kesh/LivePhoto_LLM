# LivePhoto — UAT Runtime Configuration (M5.6 §72-75)

This documents the runtime environment variables for a UAT deployment. No real office hostnames or
secrets are used — replace placeholders. Configuration is runtime (container env), not baked into
images (M5.6 §4, §53).

## Frontend environment (nginx runtime)

| Variable | Example | Meaning |
|---|---|---|
| `LIVEPHOTO_APP_ENV` | `uat` | Environment shown in runtime config |
| `LIVEPHOTO_API_BASE_URL` | `https://livephoto-api.example.internal` | Backend base URL (also used to scope CSP connect-src) |
| `LIVEPHOTO_VLM_EXPERIMENT_UI_ENABLED` | `true` / `false` | Show the VLM test panel on the Review screen (OFF by default) |

The frontend container generates `runtime-config.js` (`window.__LIVEPHOTO_CONFIG__`) at start;
no rebuild is needed to change the API URL or the VLM flag. Secrets are never written there.

Example UAT frontend env:
```env
LIVEPHOTO_APP_ENV=uat
LIVEPHOTO_API_BASE_URL=https://livephoto-api.example.internal
LIVEPHOTO_VLM_EXPERIMENT_UI_ENABLED=true
```

Normal customer configuration (identical to M5.5 UX):
```env
LIVEPHOTO_VLM_EXPERIMENT_UI_ENABLED=false
```

## Backend environment

| Variable | Example | Meaning |
|---|---|---|
| `APP_ENV` | `uat` | local/test/development/uat/production |
| `VLM_EXPERIMENT_ENABLED` | `true` | Master experiment switch (default false) |
| `VLM_UAT_LOCAL_EXPERIMENT_ENABLED` | `true` | UAT requires BOTH this AND the master switch (M5.6 §12) |
| `VLM_PROVIDER` | `local` | Provider the client selects (for UAT: local only) |
| `VLM_EXPERIMENT_LOGGING_ENABLED` | `true` | Structured request/response/error logging (M5.6 §27-32) |
| `VLM_EXPERIMENT_LOG_RAW_MODEL_TEXT` | `false` | Raw local model text (local only, non-production; M5.6 §33-34) |
| `LOCAL_VLM_BASE_URL` | `http://gemma-vlm.namespace.svc.cluster.local:8000/v1` | OpenAI-compatible base |
| `LOCAL_VLM_MODEL` | `<vision-capable-gemma-model>` | Model served by the local inference service |
| `LOCAL_VLM_API_KEY` | `<set-at-runtime>` | Auth for the local service (SecretStr) |
| `LOCAL_VLM_TIMEOUT_SECONDS` | `60` | Request timeout |
| `LOCAL_VLM_MAX_IMAGES` | `3` | Max images per request |
| `LOCAL_VLM_VERIFY_TLS` | `true` | TLS verification for the local endpoint |

Example UAT backend env:
```env
APP_ENV=uat
VLM_EXPERIMENT_ENABLED=true
VLM_UAT_LOCAL_EXPERIMENT_ENABLED=true
VLM_PROVIDER=local
LOCAL_VLM_BASE_URL=http://gemma-vlm.namespace.svc.cluster.local:8000/v1
LOCAL_VLM_MODEL=<vision-capable-gemma-model>
LOCAL_VLM_API_KEY=<set-at-runtime>
VLM_EXPERIMENT_LOGGING_ENABLED=true
VLM_EXPERIMENT_LOG_RAW_MODEL_TEXT=false
```

### Environment policy (M5.6 §11-14)

- **local / test / development**: external providers allowed when explicitly configured.
- **uat**: ONLY the self-hosted `local` provider is permitted, AND
  `VLM_UAT_LOCAL_EXPERIMENT_ENABLED=true` is required. `gemini`/`groq`/`openrouter` stay blocked
  even if keys accidentally exist.
- **production**: VLM experiment is hard-blocked regardless of configuration.

## Local Gemma

See `docs/LOCAL_GEMMA_INTEGRATION.md` for the API contract and inference-service guidance.

## MSSQL

- Mirror the official `mcr.microsoft.com/mssql/server` image into the office Artifact Registry
  (see `infrastructure/docker/IMAGE_INVENTORY.md`).
- `MSSQL_SA_PASSWORD`, `ACCEPT_EULA`, `DATABASE_URL` are runtime deployment config — never baked
  into the image (M5.6 §61).
- The app still starts without a database; SQL Server Linux requires x86-64 nodes (M5.6 §62-64).

## Transaction file storage (M5.7)

Filesystem-only (no GCS/S3). Backend writes transaction artifacts under a mounted path:

| Variable | Example | Meaning |
|---|---|---|
| `FILE_STORAGE_ROOT` | `/mnt/livephoto` | Root of transaction storage (mounted volume in UAT/prod) |

Local development:
```env
FILE_STORAGE_ROOT=./local-data/file-storage
```
Container example (same image, runtime mount):
```bash
docker run -v "$(pwd)/backend/local-data/file-storage:/data/livephoto" \
  -e FILE_STORAGE_ROOT=/data/livephoto \
  -p 8000:8000 livephoto-backend:<sha>
```
See `docs/TRANSACTION_FILE_STORAGE.md`.

## Portrait processing (M5.7)

| Variable | Example | Meaning |
|---|---|---|
| `PORTRAIT_PROCESSING_ENABLED` | `true` | Master switch |
| `PORTRAIT_BACKGROUND_MODE` | `solid` | Background mode (solid only) |
| `PORTRAIT_BACKGROUND_COLOR` | `#FFFFFF` | Solid background color |
| `PORTRAIT_CROP_MODE` | `passport` | Crop mode |
| `PORTRAIT_OUTPUT_FORMAT` | `jpeg` | Output format |
| `PORTRAIT_JPEG_QUALITY` | `95` | JPEG quality |
| `PORTRAIT_MODEL_PATH` | `/app/model-assets/modnet_photographic_portrait_matting.onnx` | Provisioned model asset (mounted) |
| `PORTRAIT_MODEL_SHA256` | `07c308cf…` | Pinned model hash |

The model asset is provisioned (not downloaded per-request) and mounted into the container; it is
never baked into the image. See `docs/PORTRAIT_PROCESSING.md`.

## M5.8 — Secure Consumer Integration runtime env

| Variable | Local dev | UAT/production (user/ops must provide) |
|---|---|---|
| `PUBLIC_LIVEPHOTO_BASE_URL` | `http://localhost:5173` | browser-facing origin |
| `CONSUMER_PROFILES_PATH` |  `./config/consumers.local.json` | mounted profile path |
| `S2S_AUTH_MODE` | `local_dev` | `jwt` |
| `S2S_LOCAL_DEV_TOKEN` | `<local secret>` | n/a (forbidden) |
| `S2S_JWT_ISSUER` / `S2S_JWT_AUDIENCE` | — | issuer / `livephoto` |
| `S2S_JWT_JWKS_URL` | (local file in test) | https JWKS URL |
| `S2S_JWT_CLIENT_ID_CLAIM` | `client_id` | per IdP |
| `LAUNCH_TOKEN_TTL_SECONDS` | `600` | 600 |
| `BROWSER_SESSION_TTL_SECONDS` | `1800` | 1800 |
| `BROWSER_COOKIE_SECURE` | `false` | `true` |
| `BROWSER_COOKIE_SAMESITE` | `strict` | `strict` |
| `CALLBACK_TIMEOUT_SECONDS` / `CALLBACK_MAX_RETRIES` | `10` / `2` | ops-approved |
| `CAPTURE_ATTEMPT_*` | `5`/`7`/`10` | ops-approved |
| `DECISION_TEST_WRITER_ENABLED` | `false` | `false` (never in uat/prod) |

UAT/production **must** use `S2S_AUTH_MODE=jwt` with a valid JWKS and `bearer_env` callback auth;
invalid/missing consumer integration fails readiness. Same-origin nginx proxies `/api` and
`/xbiz/live_photo/l/` to the backend.
