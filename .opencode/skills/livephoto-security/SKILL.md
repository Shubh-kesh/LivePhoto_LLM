---
name: livephoto-security
description: Use when reviewing LivePhoto changes for security (API, session, storage, integration, VLM/portrait/transaction work). Triggers on "security review", "audit", "vulnerability", "SSRF", "CSRF", "token", "path traversal", "PII". Produces findings with severity, file, exploit scenario, correction, and test needed.
---

# LivePhoto Security Review

Review LivePhoto integration/API/session/storage changes for security. Findings must be concrete and
actionable — never declare "secure" merely because tests pass.

## Coverage checklist

Review for:

- authentication / authorization / consumer isolation
- JWT validation, token entropy, token hashing, token expiry/revocation
- cookies, CSRF, CORS
- open redirect, SSRF
- path traversal, symlink escape
- Base64 leakage, log leakage, secret leakage
- replay/concurrency, idempotency
- callback safety (explicit timeouts; redirects not followed)
- filesystem race conditions (atomic writes, per-transaction locks)

LivePhoto-specific focus areas:

- server-authoritative decisions: browser quality/eye/VLM signals must never authorize PASS.
- transaction storage: root confinement, safe transaction IDs, no absolute paths to the frontend,
  no arbitrary file-serving endpoint.
- provider/portrait/VLM: no image bytes/Base64/keys in logs or metadata; no silent fallback to
  another provider; UAT local-only provider policy.
- frontend: no secrets in `VITE_*`, no raw error/code leakage, controlled customer language.

## Findings format

For each finding, report:

```text
severity: BLOCKER | HIGH | MEDIUM | LOW
file: <path:line if known>
behavior: <what the code does>
exploit/failure scenario: <concrete scenario>
recommended correction: <concrete fix>
test needed: <test that would have caught it>
```

Order findings by severity. If nothing is found, state explicitly what was checked and note that
"no finding" is a statement about the reviewed diff, not a blanket security guarantee.