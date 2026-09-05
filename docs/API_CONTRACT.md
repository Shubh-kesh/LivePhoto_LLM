# LivePhoto — API Contract (M0 Baseline)

Status: M0 baseline. **Conceptual contract — no implementation.** Paths and payload shapes below
are the working contract; refinements are allowed but the security properties are not.

Two audiences, deliberately separated:

- **Bank-facing API** (S2S, authenticated) — session creation and authoritative result retrieval.
- **Browser-facing flow** — capture entry and submission only; the browser never reads an
  authoritative decision.

---

## 1. Authentication expectations

| Channel | Mechanism (direction) | Notes |
|---|---|---|
| Bank → LivePhoto (`/sessions`, result API) | Authenticated S2S: client credentials / mTLS / signed requests (bank standard, open question #4) | Server-to-server only; never from browser |
| LivePhoto → Bank (callback) | Signed/authenticated callback (bank standard, open question #5) | Plus idempotency key |
| Browser capture | Opaque short-lived single-use session token issued to the redirect URL | No PII in URL; token binds session; never authoritative |
| Browser result redirect | Opaque result code + `state`; **no `is_live`/decision in URL** | Bank exchanges code via result API |

## 2. Redirect & result delivery model (preferred)

LivePhoto uses **both** delivery channels:

1. **Result API (pull)** — the bank always *can* call `GET /sessions/{id}/result` to obtain the
   authoritative decision. This is the source of truth for reconciliation.
2. **Callback (push)** — LivePhoto asynchronously posts the authoritative decision to the bank
   endpoint with retry/backoff + idempotency for automation.

Preferred primary for UX is: redirect browser with opaque code → bank pulls result. Callback
failure never loses data because the pull path always exists. This is recorded as the preferred
approach (`ADR-003`).

## 3. Endpoints (conceptual)

### 3.1 `POST /sessions`  (bank S2S)
Creates a LivePhoto session for a bank transaction. **Only the authenticated bank backend can do
this** — a browser must never create a trusted session.

- Request (conceptual): `{ "bank_correlation_id": "...", "return_url": "...",
  "expiry_seconds": <default>, "capture_config": <optional override ref> }`
- Response: `{ "session_id": "<opaque>", "capture_url": "https://lp.example/..." (opaque token),
  "expires_at": "...", "return_url_allowed": true }`
- Rules: `return_url` must be within the configured allow-list; `bank_correlation_id` is opaque to
  LivePhoto semantics (bank-owned); response never embeds PII or account data.
- Idempotency: bank supplies an idempotency key (`bank_correlation_id` or explicit) so retries do
  not create duplicate sessions.

### 3.2 `GET /sessions/{id}`  (bank S2S)
Returns session state (status, expiry, capture attempts, decision reference) for reconciliation.

### 3.3 `POST /sessions/{id}/captures`  (browser, via opaque token)
Submits the selected burst frames from the capture flow.

- Request: uploaded frames (config-bounded count/size) + opaque token.
- Response: `{ "capture_id": "...", "status": "VALIDATING", "decision_ref": null }` or a RETRY
  guidance payload. The browser never receives an authoritative PASS/FAIL semantic — it receives a
  UX-facing outcome (e.g., "please retry") that the bank re-derives server-side.
- Rules: token single-use; server validates session state, expiry, attempt budget; every frame is
  server-validated (bytes are never trusted from the client).

### 3.4 `GET /sessions/{id}/result`  (bank S2S)
Authoritative result retrieval.

- Response (conceptual):
```json
{
  "transaction_id": "...",
  "decision": "PASS",
  "is_live": true,
  "liveness_score": 0.98,
  "risk_score": 0.02,
  "quality_score": 0.96,
  "fraud_attempt": false,
  "attack_type": null,
  "reason_codes": [],
  "processing_time_ms": 1800,
  "model_versions": {},
  "threshold_version": "v1",
  "decision_id": "...",
  "decided_at": "..."
}
```
- Expiry/not-decided → explicit 404/409-style semantics (below), never a fabricated decision.

### 3.5 Callback (LivePhoto → bank, outbound)
- Payload: same `BankBusinessResult` shape + `callback_id` + `idempotency_key` + signature.
- Retry: exponential backoff, bounded attempts, dead-letter/expiry; failure is monitored and does
  not block the pull path.

## 4. Contract layers (who sees what)

| Contract | Content | Consumers |
|---|---|---|
| `InternalDecisionResult` | Full evidence: per-validator results, scores, thresholds, reason codes, versions, run metadata | LivePhoto internals, fraud/review tooling |
| `BankBusinessResult` | Decision + business-level scores + reason codes + versions (subset of internal) | Bank backend |
| `ReviewerResult` | Selected image, validation detail, reason codes, risk, history | Manual reviewer (M13), restricted |
| `AnalyticsResult` | Aggregated/anonymised performance data | Model/ops dashboards |

**Nothing above the browser**: the SPA gets only UX state. Model internals never leak to the
browser or into capture URLs.

## 5. Session & token semantics

- `session_id` opaque; capture URL token opaque; no PII.
- Short expiry (configurable; default pending confirmation).
- Single-use semantics for capture tokens; reuse → `TOKEN_REPLAY_DETECTED` security event.
- State parameter + redirect allow-list guard the return hop.
- Request integrity: tokens are bound to the session; replay protection via single-use + expiry.

## 6. HTTP status philosophy (conceptual)

| Status | Meaning |
|---|---|
| 200 | Success |
| 201 | Created (`POST /sessions`) |
| 400 | Malformed request / business validation failure (structured) |
| 401 / 403 | Missing/invalid credentials or not authorized |
| 404 | Unknown resource or already-expired session (result not available) |
| 409 | Idempotency conflict / state conflict (e.g., already decided) |
| 410 | Session expired and no result will be produced (distinct from 404) |
| 413 | Payload too large (frame limits) |
| 422 | Validation-rule violation on content (Zod/Pydantic both apply per layer) |
| 429 | Rate limit |
| 5xx | LivePhoto fault (never fabricate a decision on 5xx) |

## 7. Error model & correlation

- Structured error bodies: `{ "error_code", "message", "reason_codes", "request_id",
  "session_id?" }`. No stack traces, no PII, no raw biometrics, no tokens.
- Correlation: `request_id` (per request), `correlation_id` (per bank transaction), `session_id`.
  Propagated into logs/traces/audit (`OBSERVABILITY_STRATEGY.md`).

## 8. Rate limits & abuse posture

- Per-bank-client rate limits on S2S endpoints; per-session and per-token limits on capture path;
  body-size limits; anomaly events (`RATE_LIMIT_TRIGGERED`). See `SECURITY_REQUIREMENTS.md`.

## 9. Open items (recorded, not blockers)

- Exact callback auth (question #5), bank endpoint ownership, idempotency-key format, default
  expiry values, return-URL allow-list administration model, and whether the bank prefers
  callback-first or pull-first UX — pending bank confirmation in M10.

## 10. M1 refinements (foundation contracts)

Recorded during M1 so later milestones implement against stable contracts. No implementation
exists yet.

### 10.1 Callback event envelope

Every outbound callback carries a stable event envelope (idempotency-safe):

```json
{
  "event_id": "<opaque, unique per event>",
  "event_type": "LIVEPHOTO.DECISION.CREATED",
  "transaction_id": "<bank correlation>",
  "decision_id": "<LivePhoto decision id>",
  "occurred_at": "<ISO-8601>",
  "payload": { }
}
```

Contract properties:
- `event_id` is unique per event; the bank endpoint can use it to deduplicate (idempotency).
- Delivery state is tracked: `PENDING / SENT / ACKNOWLEDGED / FAILED / EXPIRED` with
  `attempt_count`, `next_retry_at`, `last_error` (see `DATA_MODEL.md` `IntegrationCallback`).
- Retry uses bounded exponential backoff; terminal failure does not lose data because the result
  is always retrievable via `GET /sessions/{id}/result`.
- Acknowledgement is explicit (bank acks the callback or pulls the result); audit history records
  every delivery attempt. Callback authentication remains an open item (question #5).

### 10.2 Decision identity

- Every decision carries its own `decision_id`, distinct from `transaction_id` (the bank
  correlation) and `session_id`.
- Rationale: retry/review/version scenarios may produce multiple decision-related records for one
  transaction; `transaction_id` alone is not a stable unique identity for a decision.
- External contracts expose `decision_id` alongside `transaction_id`.

### 10.3 Capture credential contract

The future browser capture credential must satisfy, by design:

- **Opaque or appropriately signed** — an opaque random token is the default option; JWT is not
  chosen merely because it is common.
- **Short-lived** — expires quickly; configurable, pending confirmation.
- **Session-specific** — bound to exactly one LivePhoto session.
- **Narrowly scoped** — only permits capture submission for that session.
- **Revocable/invalidatable** — invalidated by session state transitions (expiry, cancellation,
  decision) and by single-use semantics; reuse triggers `TOKEN_REPLAY_DETECTED`.
- **Safe for browser possession** — the browser holds it, so it must not grant access to bank
  integration APIs, other sessions, administrative APIs, review APIs, or internal analytics.

The capture credential is separate from bank S2S credentials; the two trust models are never
merged (see `backend/app/integrations/` docstring).
