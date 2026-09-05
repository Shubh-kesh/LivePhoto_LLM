# LivePhoto — Security Requirements (M0 Baseline)

Status: M0 baseline. Requirements are separated into **POC** and **production**. POC security is
real but proportional; production requirements are the target bar. External AI providers are
POC-only unless separately approved (see `DATA_GOVERNANCE.md`).

The browser is untrusted and the server is authoritative (`ARCHITECTURE_PRINCIPLES.md` P2/P3).
Client-side checks are UX/preliminary screening only.

---

## 1. POC requirements

| Area | Requirement |
|---|---|
| Transport | HTTPS everywhere; HSTS; no mixed content |
| Capture | Camera requires HTTPS-or-secure-context (localhost excepted in dev); permission flow handled by browser |
| Browser handling | Reasonable CSP/CORS for the POC origin; no PII in URLs; opaque session tokens |
| Secrets | Keys for external providers in env/secret store, never in source, never committed |
| Data | Only approved demo/synthetic images may reach external VLM; no bank data in POC |
| Logging | No tokens, no raw biometrics, no PII in logs |
| Baseline hygiene | Dependencies pinned; known-vulnerability scan on build images (basic); no default creds |

## 2. Production requirements (application)

| Area | Requirement |
|---|---|
| TLS | TLS 1.2+ enforced end-to-end; strong cipher suites; cert management automated; HSTS |
| Authentication (S2S) | Bank backend authenticated per bank standard (mTLS or client-credentials or signed requests — open question); never browser-issued credentials |
| Authorization | Least privilege; service identities per component; reviewers get scoped roles (M13); no tenant-wide admin by default |
| Session security | Opaque session tokens; short expiry; single-use capture tokens; replay protection; session binding; no PII in URLs (`API_CONTRACT.md`) |
| Token security | Tokens stored securely; never in logs/referrer; `Referrer-Policy`; bounded lifetimes |
| CORS | Strict allow-list of LivePhoto origin(s); credentials policy; preflight handling; no wildcard in production |
| CSP | Strict CSP for the SPA; no unsafe-inline/unsafe-eval unless justified and reviewed; frame-ancestors to defeat clickjacking |
| CSRF | State-changing endpoints protected (token/state parameters); SameSite cookies where cookies are used |
| XSS | Output encoding; CSP; React default escaping; no `dangerouslySetInnerHTML` without review |
| Clickjacking | `frame-ancestors` CSP / `X-Frame-Options`; WebView `allow-navigation` restrictions |
| Redirect allow-listing | Return URLs validated against a configured allow-list; open-redirect tests in CI |
| Rate limiting | Per-bank-client, per-session, per-token limits; request size limits; anomaly events |
| Request limits | Body size, frame count, per-session attempt budget enforced server-side |
| File/image validation | All uploads server-validated: type, size, dimension bounds, frame count, integrity; never trust client claims |
| Error handling | Structured errors, no stack traces/PII/tokens/biometrics in responses or logs |
| Secrets management | Externalized; secret manager; rotation; no secrets in code/config images/env dumps |
| Logging & audit | Structured, correlatable (`request_id`/`correlation_id`/`session_id`), redacted; full event registry (§4) |
| Session integrity | Any security-relevant event recorded as audit event; session state transitions guarded |

## 3. Production requirements (infrastructure)

| Area | Requirement |
|---|---|
| Secret management | Managed secret store; least-privilege access; rotation |
| Encryption | Data encrypted in transit (TLS) and at rest (DB + object storage); key management per policy |
| Network segmentation | Internal zones separated by network policy; only the ingress/edge reachable from Internet; egress restricted (POC VLM egress only from POC env) |
| Service accounts / IAM | Per-component identities; least privilege; no long-lived static keys where avoidable |
| Container/image scanning | Registry scanning; base-image patching; signed images where available |
| Dependency scanning | CI dependency vulnerability scanning |
| SAST / DAST | SAST in CI on the application; DAST against deployed environments before release gates |
| VA/PT | Periodic vulnerability assessment and penetration test per bank schedule |
| Ingress/WAF | Bank-approved ingress/WAF standard (open question #6); TLS termination; request limits |
| Backup & recovery | Backups of MSSQL and object-storage metadata per RPO/RTO (to be fixed — open question #3); restore testing |
| Access review | Periodic access reviews for operators/reviewers/admins |

## 4. Security/audit event taxonomy (registry)

Structured event types (`AuditEvent.event_type`). Extensible only through the registry; no ad hoc
types.

```
SESSION_CREATED
SESSION_OPENED
CAMERA_PERMISSION_GRANTED
CAMERA_PERMISSION_DENIED
CAPTURE_STARTED
CAPTURE_COMPLETED
VALIDATION_STARTED
VALIDATION_COMPLETED
DECISION_CREATED
CALLBACK_SENT
CALLBACK_FAILED
SESSION_EXPIRED
TOKEN_REPLAY_DETECTED
RATE_LIMIT_TRIGGERED
INVALID_REDIRECT_ATTEMPT
REVIEW_CREATED
REVIEW_COMPLETED
DATA_DELETED
MODEL_VERSION_CHANGED
THRESHOLD_VERSION_CHANGED
```

**Never logged:** raw access tokens, secrets, full customer PII, raw biometric images.
Biometric objects are referenced by opaque IDs/hashes only (`DATA_GOVERNANCE.md`,
`OBSERVABILITY_STRATEGY.md`).

## 5. Trust-boundary controls summary

See `SYSTEM_CONTEXT.md` §4 (TB-1…TB-7). Notable points:

- TB-1 (browser): server authority; token discipline; rate limits; CSP/CORS; capture validation.
- TB-2 (bank peer): authenticated S2S; redirect allow-list; signed callbacks; idempotency; result
  pull path always available.
- TB-3 (internal): network policy; service identity; edge authentication.
- TB-4 (external VLM): POC-only, demo data only, restricted egress, contractual/security review.
- TB-5 (MSSQL/object storage): private buckets; encryption; least privilege; signed access only;
  access logging.
- TB-6 (reviewers, future): RBAC + audit + minimised data exposure.
- TB-7 (observability): redaction; no PII/biometrics in metrics/logs/labels.

## 6. Assumptions & items for confirmation

- Production WAF/ingress standard, S2S auth standard, callback auth, RPO/RTO, and key-management
  ownership are **open stakeholder questions** (`SYSTEM_CONTEXT.md` §7), not assumed solved.
- Regulatory applicability (RBI/DPDP/other) is asserted by bank compliance/legal, not by this
  document.
- WebViews are treated as untrusted browser surfaces with additional navigation restrictions
  where feasible.