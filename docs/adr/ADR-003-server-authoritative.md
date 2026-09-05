# ADR-003 — Server-Side Authoritative Decision

- **Status:** Accepted
- **Date:** M0

## Context
The browser is untrusted and can be manipulated (DevTools, injected JS, virtual cameras, modified
binaries). If the client alone decided liveness, spoofs could self-approve. The bank must obtain
an authoritative decision from the LivePhoto backend.

## Decision
The authoritative liveness decision is computed and **persisted server-side**. The browser only
handles UX and preliminary screening; client-side PASS is never authoritative. After completion,
LivePhoto redirects the browser to an allow-listed bank return URL carrying **only an opaque code /
state — never `is_live=true` or a decision**. The bank independently obtains the authoritative
result via the **result API (pull)** and, optionally, a **signed callback (push)**; the pull path
always remains available so callback failure never loses the result.

## Alternatives considered
- **Client-decides, redirect carries `is_live=true`** — rejected: trivially spoofable (P3).
- **Callback-only** — rejected: if delivery fails the bank has no result; pull path is the
  reconciliation safety net.
- **Push-only to bank** — rejected for the same reason; both are supported, pull is the source of
  truth.

## Consequences
- All security-relevant validation must run server-side (frames are server-validated, never
  trusted from the client).
- Bank integration must be S2S-authenticated; session creation is bank-initiated only.
- Design cost: an authenticated result channel and callback with idempotency/retry.

## Future review triggers
- When bank auth/callback standards are confirmed (open questions #4/#5), align the mechanism.
