# LivePhoto — Data Governance (M0 Baseline)

Status: M0 baseline. Establishes data classes and handling rules. **No biometric retention
duration is invented here**; retention values are placeholders requiring bank legal/compliance
sign-off. Regulatory/legal classification is to be confirmed by the bank's compliance/legal/
security teams — this document claims no compliance by itself.

---

## 1. Data classification

| Class | Examples | Handling emphasis |
|---|---|---|
| Biometric / sensitive image data | Burst frames, final selected photograph | Object storage only, encrypted, private, strict access, lifecycle-managed, never logged/duplicated |
| Security-sensitive metadata | Decision, scores, reason codes, versions, session status, validation results | MSSQL, immutable decisions, audited access |
| Transaction metadata | Bank correlation ID, timestamps, session references | MSSQL; no PII in URLs/logs |
| Operational telemetry | Latency, error rates, resource usage | Prometheus/OTel; no PII/biometrics; low-cardinality labels |
| Audit data | Audit events | Immutable, long-lived, protected |
| Model analytics data | Aggregated benchmark/validator analytics | Aggregated/anonymised; no identity attributes |

## 2. Collection

- Camera capture only (V1); gallery/file upload disabled.
- Client sends frames/telemetry with user consent as presented by the bank journey; capture is the
  minimum necessary data for liveness.
- Client telemetry is treated as untrusted hints, never authoritative, and minimised.

## 3. Storage

- Images → approved object storage (private buckets, encryption, access logging, signed access
  only). **No public biometric URLs.**
- Metadata/decisions/scores/versions/audit → MSSQL.
- No Base64 production images in primary MSSQL business tables (`ADR-006`).
- No raw biometric data in logs, metrics labels, error payloads, or support dumps.

## 4. Transmission

- TLS in transit everywhere; S2S authenticated; callback signed/authenticated; egress restricted.
- External AI providers: **POC-only**, approved demo images only; bank testing and production data
  must not be sent to external providers without explicit security/legal/compliance approval.

## 5. Retention (placeholders — require bank approval)

M1 distinguishes three image lifecycle classes with **independent** retention semantics
(M1 §70; `VALIDATION_PIPELINE.md` §Capture):

| Class | What it is | Default intent | Retention placeholder | Requires |
|---|---|---|---|---|
| Transient burst frame | Raw frames from the 1–2 s burst used for screening/selection | Delete/expire rapidly per policy; do not retain every frame just because storage exists | **[TBD — bank-confirmed]** | Legal/compliance sign-off |
| Selected final capture | The single customer photograph chosen as the product of the session | Governed by biometric-image retention | **[TBD — bank-confirmed]** | Legal/compliance sign-off |
| Retained fraud/review evidence | A small, configurable subset kept for investigation/review (M13) | Longer-lived than transient frames; access-restricted | **[TBD — bank-confirmed]** | Legal/compliance + audit requirements |

Other classes:

| Class | Retention placeholder | Requires |
|---|---|---|
| Session/capture/decision metadata | **[TBD]** | Legal/compliance sign-off |
| Audit events | **[TBD]** | Legal/compliance + audit requirements |
| Callback records | **[TBD]** | Bank reconciliation needs |
| Analytics (aggregated) | **[TBD]** | Compliance sign-off |

Retention is configurable and **versioned** (`policy_version`), with lifecycle states
(active / pending-delete / deleted) recorded in `RetentionRecord` (`DATA_MODEL.md`).

## 6. Deletion

- Auditable lifecycle management; deletion is an event (`DATA_DELETED`) with authorization
  reference; silent `DELETE` is not permitted.
- Deletion must handle both the object-store object and its metadata references coherently.

## 7. Access

- Least privilege; per-component service identities; role separation for reviewers/operators/admins.
- Manual review (M13) access restricted to authorised reviewers, fully audited.
- No bulk export of biometric data; egress controls; access reviews periodic.

## 8. Audit

- Every security-relevant and lifecycle event recorded (`SECURITY_REQUIREMENTS.md` §4 registry).
- No raw tokens, secrets, PII, or biometric bytes in audit payloads.

## 9. Test data & production data separation (zones)

```
POC/demo data     - open/synthetic/non-sensitive; external-VLM allowed
Bank testing data - bank-internal genuine+spoof; controlled; NOT auto-copied to public dev; NOT sent external by default
Production data   - live captures; self-hosted inference only
```

Transfer between zones requires approval; automation must not silently copy across zones.

## 10. Model-improvement approval

- Using production (or bank-testing) biometric samples to train or fine-tune any model requires
  explicit approval under the model-improvement policy; default is no reuse without approval.
- Only de-identified/aggregated analytics flow to dashboards without approval.

## 11. External AI restrictions (summary)

- POC: approved demo images → Gemini/OpenRouter/Groq permitted under POC policy.
- Bank testing: not permitted by default.
- Production: self-hosted model inside bank-controlled infrastructure; no external third-party AI
  API dependency unless separately approved.

## 12. Data-subject considerations

- LivePhoto stores a photograph of the customer (biometric data). The bank journey must present
  appropriate consent/information per applicable law; exact text/flow is bank-owned. DPDP/other
  applicability is confirmed by bank compliance (open question #12).
