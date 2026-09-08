# LivePhoto — Consumer Callback Contract (M5.8)

A success-only callback is delivered to the trusted consumer callback URL when the user submits a
canonical PASS with a valid processed portrait. No callback is sent for quality failure,
spoof/retry, uncertain, technical failure, or attempt-limit states.

## Payload

```json
{
  "event_id": "<sha256(consumer_id:external_transaction_id:LIVEPHOTO.DECISION.CREATED)>",
  "transaction_id": "<external transaction id>",
  "decision_id": "<canonical decision id>",
  "occurred_at": "<ISO-8601>",
  "processed_jpeg_base64": "<Base64 of portrait/processed.jpg, in memory only>",
  "processed_jpeg_sha256": "<SHA-256 of the JPEG>"
}
```

- MIME `image/jpeg`.
- Base64 is encoded in memory during transport only; it is **never persisted** and **never logged**.
- `event_id` is the stable Idempotency-Key sent as `Idempotency-Key: <event_id>` on every retry.

## Auth

- `auth_type: none` — local/test only.
- `auth_type: bearer_env` — `Authorization: Bearer <secret>` where the secret is resolved from
  `callback.secret_env`; required in UAT/production.

## Transport / retry

- `httpx` with an explicit timeout (`CALLBACK_TIMEOUT_SECONDS`) and **redirects disabled**
  (`follow_redirects=False`).
- Retries only transient failures (timeout, connection, HTTP 429, HTTP 5xx) up to
  `CALLBACK_MAX_RETRIES`. Deterministic 4xx (except 429), invalid JSON, invalid redirect, and any
  3xx are terminal.
- Double Submit does not create a second callback: an acknowledged callback is deduplicated via the
  stored `callback/decision-callback.json` state.
- On failure the workflow becomes `CALLBACK_FAILED`; the user may Submit again and the same
  `event_id` is retried (no recapture).

## Response / redirect

Expected response:

```json
{ "redirect_url": "https://approved-consumer-origin/..." }
```

The redirect URL is validated server-side against the consumer profile's `allowed_redirect_origins`
by **exact origin** (scheme+host+port, HTTPS outside local, no userinfo). After a successful
callback + valid redirect, the workflow becomes `COMPLETED` and active launch/session state is
revoked. The frontend receives only the backend-validated redirect URL and navigates to it.
