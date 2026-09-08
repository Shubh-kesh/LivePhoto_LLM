# LivePhoto — Secure Consumer Integration Architecture (M5.8)

## Same-origin topology

M5.8 deploys the browser flow on a single origin. The browser-facing origin serves the React SPA and
proxies backend paths:

```text
https://<livephoto-origin>/
    /xbiz/live_photo/          React SPA (IntegrationPage)
    /xbiz/live_photo/l/<token> backend launch redemption (302 -> clean URL)
    /api/                      backend APIs (S2S launch/status + browser API)
```

- **Container (nginx):** `location /api/` and `location /xbiz/live_photo/l/` proxy to the backend;
  `/xbiz/live_photo/` falls through to `index.html` (SPA).
- **Local dev (Vite):** `server.proxy` forwards `/api` and `/xbiz/live_photo/l` to FastAPI.
- `PUBLIC_LIVEPHOTO_BASE_URL` is the **browser-facing origin** (local: `http://localhost:5173`).
  The backend never returns `localhost:8000` as a launch URL.

## Flow

```text
Consumer backend --S2S JWT/local_dev--> POST /api/v1/integration/launch-sessions
    -> LivePhoto creates internal transaction (folder BEFORE capture)
    -> mints opaque launch token (>=256-bit, SHA-256 persisted)
    -> returns launch_url
Browser --GET /xbiz/live_photo/l/<token>--> validate -> create browser session + CSRF
    -> 302 to /xbiz/live_photo/ (clean URL)
Capture -> /browser/capture (attempt_id) -> canonical PASS -> /browser/portrait
    -> preview -> POST /browser/submit -> callback (Base64 in memory) -> redirect
```

## Trust boundaries

| Boundary | Auth |
|---|---|
| S2S launch / status | JWT (`S2S_JWT_CLIENT_ID_CLAIM` -> `jwt_client_ids`) or local_dev (local/test/dev only) |
| Redemption | Opaque launch token (hash-only) |
| Browser API | HttpOnly `lp_session` cookie + session-bound `lp_csrf` CSRF |
| Callback | consumer profile URL, `bearer_env`/`none`, stable Idempotency-Key |

Server-authoritative decisions: only a persisted canonical `DecisionOutcome.PASS` authorizes Submit.
The experimental VLM result is never consulted for submission.

## Reopenable launch token (contract change)

The M5.8 launch token is a **reopenable launch capability token**, not a one-time capture token. It
remains valid until expiry, reissue, completion, cancellation, or attempt-limit terminal state. Each
successful redemption creates a fresh browser session and invalidates the previous active one.

## Filesystem layout

```text
<FILE_STORAGE_ROOT>/
  transactions/<internal_tx_id>/transaction.json, capture/, portrait/, decisions/,
      launch/active-launches.json, browser/active-session.json, attempts.json,
      callback/decision-callback.json, .lock
  index/launch-tokens/<sha256>.json
  index/browser-sessions/<sha256>.json
  index/external/<sha256(consumer:external)>.json
```

All state is shared-filesystem and atomic; external transaction IDs never appear in paths.
