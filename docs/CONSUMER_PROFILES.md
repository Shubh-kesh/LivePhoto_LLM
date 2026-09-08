# LivePhoto — Consumer Profiles (M5.8)

Consumer profiles are backend configuration (no DB). The committed
`backend/config/consumers.example.json` holds safe placeholder values (`active: false`). Real
profiles are mounted/ignored (`backend/config/consumers.local.json` is gitignored).

## Schema

```json
{
  "consumer_id": "D365",
  "active": true,
  "name": "...",
  "jwt_client_ids": ["d365-livephoto-client"],
  "callback": { "url": "https://...", "auth_type": "bearer_env", "secret_env": "D365_CALLBACK_BEARER_TOKEN" },
  "allowed_redirect_origins": ["https://..."],
  "request_policy": {
    "ocr_required": [false],
    "camera_configs": ["1"],
    "white_background": [true],
    "output_formats": ["jpeg"]
  },
  "max_attempts": 10,
  "watermark_spec": null
}
```

## Rules

- `auth_type` is `none` (local/test only) or `bearer_env` (everywhere; required in UAT/production).
- The callback bearer value is resolved at runtime from the environment variable named by
  `callback.secret_env` — **never stored in the profile JSON**.
- Inactive consumers cannot launch.
- Launch request options are validated against `request_policy`; unsupported options are rejected,
  never silently ignored.
- `allowed_redirect_origins` is matched by exact origin (no substring / no endsWith).

## Local setup

```bash
cp config/consumers.example.json config/consumers.local.json   # from backend/
# edit consumers.local.json: set active=true, auth_type=none (local), a local callback URL,
# and allowed_redirect_origins (e.g. http://localhost:3001)
```

Point `CONSUMER_PROFILES_PATH` at `./config/consumers.local.json` (relative to the backend cwd
`backend/`) for local runs. UAT/prod
mount the real profile file (never baked into images).
