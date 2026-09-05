# LivePhoto — Observability Strategy (M0 Baseline)

Status: M0 baseline. Defines the telemetry **contract** now so that later dashboards (M14/M15)
have the right data from day one. Tools: Prometheus, OpenTelemetry, structured logging. No
dashboard implementation in M0.

**Cardinality & privacy rules (fixed):**
- Avoid metrics with uncontrolled cardinality (e.g., per-customer labels).
- **Never** place raw customer identifiers or PII into Prometheus labels or metric names.
- Never log raw biometric images, tokens, or secrets.
- Use low-cardinality class labels (device class, browser class, OS class, camera class), not raw
  user-agent strings or device serials.

---

## 1. Correlation & identity in observability

- `request_id` — per HTTP request (generated at edge, propagated).
- `correlation_id` — per bank transaction (bank-owned, opaque).
- `session_id` — per LivePhoto session (opaque).
- `transaction_id` — per bank transaction (alias/correlation context).
- These propagate into logs, traces, and audit events. Metrics use only low-cardinality facets
  plus these opaque IDs where a trace/log pivot is needed (not as metric labels).

## 2. Application observability (service health)

- HTTP latency (p50/p95/p99) and error rate by route.
- Dependency latency/errors: MSSQL, object storage, VLM provider, callback endpoint.
- Database latency; object-storage latency; callback latency and failure rate.
- Pod CPU/memory, queue depth (if introduced), 5xx/4xx rates, rate-limit triggers.

## 3. ML observability (decision health)

- Per-validator: score distribution, result distribution, latency, model version.
- Decision distribution: PASS/RETRY/REVIEW/FAIL rates.
- Confidence distribution; calibrated-score distribution.
- Model disagreement rate (`MODEL_DISAGREEMENT` reason-code frequency).
- Attack-type distribution (where detected), reason-code frequency.
- Drift signals: score-distribution drift, near-miss attacks, threshold proximity.
- Version mix: which model/prompt/threshold versions are serving, so regressions are attributable
  to a version (pairs with `DATA_MODEL.md` versioning).

## 4. Security observability

- Session anomalies (unexpected expiry/replay): `TOKEN_REPLAY_DETECTED`, `SESSION_EXPIRED`,
  `INVALID_REDIRECT_ATTEMPT`, `RATE_LIMIT_TRIGGERED`.
- Unexpected callback activity / callback failures.
- Suspicious capture patterns (attempt bursts, abnormal frame rejection).
- AuthN failures on S2S endpoints.
- Config/version changes (`MODEL_VERSION_CHANGED`, `THRESHOLD_VERSION_CHANGED`) with actor.

## 5. Logging

- Structured JSON logs with correlation IDs and redaction.
- Levels: DEBUG/INFO/WARN/ERROR/CRITICAL; security events logged at a guarded level with their own
  registry (`SECURITY_REQUIREMENTS.md` §4).
- No secrets/tokens/PII/biometrics in any log field; `input_reference` is opaque.

## 6. Tracing

- OpenTelemetry traces across: browser capture upload → API → orchestrator → each validator →
  VLM → persistence → callback.
- Span attributes use low-cardinality values; validator/model versions as span attributes are
  acceptable (low cardinality), raw scores only as coarse buckets if needed.

## 7. Alert concepts (to be specified in M14)

- Error-rate SLO breach (p95 latency and error budget for the <5 s decision path).
- Validator outage/timeout spike; VLM timeout spike; PAD crash.
- Abrupt PASS/FAIL/RETRY distribution shift; reason-code anomaly.
- Replay/redirect/rate-limit event spikes; callback failure rate.
- Drift on score distribution; new near-miss cluster.

## 8. Dashboard concepts (M15)

- Executive: transaction counts, PASS/RETRY/REVIEW/FAIL rates, attack types, false positives,
  false negatives, review reversals, per-browser/device/OS/camera breakdowns, latency.
- Model: per-validator performance, model-version comparison, threshold-version comparison,
  confidence/score distributions, drift, near-miss.
- Security: anomaly counters, replay/redirect/rate-limit, callback health, version-change audit.

## 9. Operational telemetry list (consolidated)

API latency; API error rate; pod CPU; pod memory; inference latency; queue depth (if introduced);
database latency; object-storage latency; external-provider latency; callback failures; upload
latency; VLM token/cost (POC).

## 10. Guardrails

- Metric cardinality review as part of any new metric (CI check where feasible).
- PII/biometric content is blocked from metrics/logs by construction; scan in CI (regex/SAST) for
  accidental PII/token fields.
- Observability of the *decision* is as important as observability of *uptime*; both are
  first-class.
