# LivePhoto — Non-Functional Requirements (M0 Baseline)

Status: M0 baseline. Each requirement is classified **MUST / SHOULD / COULD**. Latency budget,
scale, availability, scalability, security, privacy, auditability, maintainability, testability,
observability, browser compatibility, accessibility, recoverability.

---

## 1. Latency

| Req | Class | Detail |
|---|---|---|
| Capture → final decision < 5 s | **MUST** | Hard business cap; p95 < 5 s. Target p95 < 4 s (bands in `VALIDATION_PIPELINE.md` §13) |
| Validator timeouts bounded | **MUST** | VLM timeout short enough not to blow the cap while preserving fail-safe semantics |
| Decision under accuracy priority | MUST | Accuracy takes priority within the 5 s boundary; never shave accuracy to hit latency |

## 2. Scale

| Req | Class | Value |
|---|---|---|
| Daily transactions | MUST | ≈ 20,000 |
| Peak requests | MUST | ≈ 180 transactions/min |
| Concurrent capture sessions | MUST | ≈ 5 |
| Inference independently scalable | MUST | Validation/inference service(s) scalable separately from API (HPA) |
| Not over-engineered for millions | MUST | No distributed complexity for load we don't have (P16) |

### Bottleneck watch-list (recorded, addressed in M19)

API; database; object storage; external VLM APIs (POC); CPU inference; GPU inference; network
upload; callback processing. Each is monitored per `OBSERVABILITY_STRATEGY.md`.

## 3. Availability

| Req | Class | Detail |
|---|---|---|
| No single point of failure in API/db/object storage/inference/ingress/secrets/monitoring | SHOULD | Production HA posture; modular monolith with replica counts |
| RPO/RTO | MUST (placeholder) | Values to be fixed with banking infra stakeholders (open question #3); backup expectations documented |
| Regional cluster | SHOULD | GCP region; not multi-region DR unless justified |
| PDB / readiness / liveness / resource limits | SHOULD (production) | `SYSTEM_CONTEXT.md` §3 |

## 4. Scalability

| Req | Class | Detail |
|---|---|---|
| HPA | **MUST** (production) | Required; consider CPU, memory, request rate, inference queue depth, inference latency, custom metrics (P16) |
| Inference workers independent of API | MUST | `SYSTEM_CONTEXT.md` §5 |
| Graceful handling of capture bursts | SHOULD | ~5 concurrent; burst uploads bounded by config |

## 5. Security

Security is covered by `SECURITY_REQUIREMENTS.md` (MUST-level by default for production). Cross
reference: TLS, authentication, authorization, session/token, CORS/CSP/CSRF/XSS/clickjacking,
redirect allow-listing, rate limiting, request limits, image validation, secret management,
encryption, logging, audit, scanning (dependency/container/SAST/DAST/VA/PT), least privilege,
service accounts, network segmentation.

## 6. Privacy

| Req | Class | Detail |
|---|---|---|
| Privacy by design | MUST | No PII/biometrics in logs/metrics/URLs; data classification honored |
| Image storage separation | MUST | Object storage for images; MSSQL metadata (`ADR-006`) |
| External AI restriction | MUST | POC/demo-only, approved images; production self-hosted (`DATA_GOVERNANCE.md`) |

## 7. Auditability

| Req | Class | Detail |
|---|---|---|
| Immutable, versioned decisions | MUST | Reproducible from recorded versions |
| Full security event registry | MUST | `SECURITY_REQUIREMENTS.md` §4 |
| Lifecycle/audit of deletion | MUST | `DATA_MODEL.md` RetentionRecord |

## 8. Maintainability

| Req | Class | Detail |
|---|---|---|
| Modular monolith first | MUST | `ADR`/P14; extract services only when justified |
| Replaceable validators | MUST | Validator contract (P5) |
| Configuration over hardcoding | MUST | P10; versioned config catalogue (`SYSTEM_CONTEXT.md` §6) |

## 9. Testability

| Req | Class | Detail |
|---|---|---|
| `MockVisionProvider` | MUST | Offline pipeline testing |
| Same harness for A/B/C | MUST | `MODEL_EVALUATION_STRATEGY.md` |
| Disjoint-split discipline | MUST (once training) | `MODEL_EVALUATION_STRATEGY.md` §10 |

## 10. Observability

| Req | Class | Detail |
|---|---|---|
| Metrics/logs/traces + ML + security telemetry | MUST | `OBSERVABILITY_STRATEGY.md` |
| Low-cardinality, no PII labels | MUST | Fixed rule |
| Every validator observable | MUST | Normalized `ValidationResult` carries score/threshold/version/latency |

## 11. Browser & device compatibility

| Req | Class | Detail |
|---|---|---|
| Android mobile browsers, iPhone browsers | MUST | |
| Android/iOS WebView where feasible | SHOULD | Treated as untrusted browser surface |
| Windows/macOS laptops (webcam) | MUST | |
| Front/rear mobile camera, laptop webcam | MUST | |
| Exact supported browser/OS matrix | COULD (open) | To be confirmed with bank device policy (question #10) |

## 12. Accessibility

| Req | Class | Detail |
|---|---|---|
| Capture guidance readable/operable by assistive tech | SHOULD | WCAG-aligned guidance, focus management, non-flash-only feedback |
| Colour not the only signal for guidance states | SHOULD | Also icons/text |

## 13. Recoverability

| Req | Class | Detail |
|---|---|---|
| Result retrievable via pull path even if callback fails | MUST | `API_CONTRACT.md` §2 |
| Callback retry + idempotency | MUST | |
| Backups per RPO/RTO | MUST (placeholder) | Fixed with infra stakeholders |
| Restore testing | SHOULD | |

## 14. Assumptions

- Numbers are planning figures; reconfirm with bank at M10/M19.
- Availability/RPO/RTO are placeholders pending banking infra sign-off (open questions).
- Browser matrix pending bank device policy.