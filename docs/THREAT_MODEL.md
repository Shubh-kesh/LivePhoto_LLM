# LivePhoto — Threat Model (M0 Baseline)

Status: M0 baseline. Living document; updated as validators, data flows, and deployment change.

This model is a **structured threat assessment**, not a guarantee. Residual risk is reported
explicitly, per attack, because LivePhoto's most important security property is *measured* spoof
rejection with attack-specific reporting (`PRODUCT_REQUIREMENTS.md` §Success criteria).

---

## 1. Methodology

Asset-centric STRIDE-style analysis: enumerate assets, actors, trust boundaries, entry points, and
threat categories; score each scenario; assign controls; record residual risk and future controls.
Trust boundaries TB-1…TB-7 are defined in `SYSTEM_CONTEXT.md` §4.

## 2. Assets

| # | Asset | Classification | Where it lives |
|---|---|---|---|
| A1 | Live session validity (the "is a live person present" answer) | Security-sensitive | Backend decision records |
| A2 | Capture frames + final selected photograph | **Biometric/sensitive image data** | Object storage (encrypted, private) |
| A3 | Capture/session/validation metadata | Security-sensitive metadata | MSSQL |
| A4 | Validator/model/prompt/threshold config + versions | Security-sensitive (tamper = decision corruption) | MSSQL / config store / VCS |
| A5 | API credentials, signing keys, provider keys | Secret | Secret manager |
| A6 | Bank correlation ID + transaction ID | Transaction metadata | MSSQL (no PII in URLs) |
| A7 | Callback/redirect channels to bank | Transaction metadata | Network (authenticated) |
| A8 | Review cases + reviewer decisions (future) | Security-sensitive + biometric refs | MSSQL + object storage refs |
| A9 | Audit events | Audit data | MSSQL / log store |

**Crown jewels:** A1 (integrity), A2 (privacy), A4 (integrity). A2 must never be reachable via
public URL or leak into logs.

## 3. Actors

| Actor | Description | Trust |
|---|---|---|
| Customer | Legitimately completes capture | Untrusted (may be attacker) |
| Attacker (remote fraudster) | Spoofs via photo/print/screen/video/injection | Untrusted, adversarial |
| Attacker (technical) | Manipulates browser, network, API | Untrusted, adversarial |
| Bank Backend | Initiates/consumes sessions | Semi-trusted peer (authenticated) |
| LivePhoto operators/SRE | Operate service | Internal, trusted-but-audited |
| Fraud/model team | Review cases, set thresholds | Internal, trusted-but-audited |
| Manual reviewer (future) | Reviews REVIEW cases | Internal, restricted |
| VLM provider (POC) | External inference | External, not trusted with bank/prod data |
| Cloud provider | Runs infrastructure | Trusted processor (contractual) |

## 4. Entry points

| # | Entry point | Who | Boundary |
|---|---|---|---|
| E1 | LivePhoto UI (SPA, redirect entry) | Customer browser | TB-1 |
| E2 | Capture upload endpoint | Browser/WebView | TB-1 |
| E3 | Session management API (`/sessions`) | Bank backend | TB-2 |
| E4 | Result retrieval API | Bank backend | TB-2 |
| E5 | Callback delivery outbound (LivePhoto → bank) | LivePhoto | TB-2 |
| E6 | Object storage access | Services only | TB-5 |
| E7 | Observability/log stores | Operators | TB-7 |
| E8 | Manual review UI (future) | Reviewers | TB-6 |
| E9 | Admin/config APIs | Operators | Internal |

## 5. Threat categories

### 5.1 Presentation attacks (PRES)
Physical artefacts presented to a real camera. **In Phase-1 scope:** photograph displayed on a
mobile/tablet/laptop-monitor; printed photo; photo in newspaper/magazine. **Deferred:** video
replay on screens, high-res OLED, curved/bent prints, cut-eye, paper/3D/silicone/partial masks.

### 5.2 Digital injection attacks (INJ)
Fake camera feed into a *real* capture session: virtual camera, OBS, ManyCam, prerecorded media
injection, camera-stream injection, camera API hooking; plus deepfake/AI-generated faces. All
deferred, but the architecture must not accidentally "bless" injected media as authoritative.

### 5.3 Client/browser manipulation (CLIENT)
DevTools tampering, JS injection, spoofed device/browser signals, fake permissions, scripted
upload replay. Browser is untrusted (P3); client claims are never authoritative.

### 5.4 Backend/API abuse (API)
Unauthenticated/untrusted session creation, capture upload forgery, session/result replay,
redirect manipulation, malicious or forged callbacks, token leakage reuse, rate abuse.

### 5.5 Operational / insider threats (OPS)
Insider misuse of biometric data or review tooling, config/model/prompt tampering, credential
exposure, data exfiltration via object storage/logs, DoS of the service.

## 6. Attack scenarios & risk register

Likelihood/Impact: **L/M/H** (pre-control likelihood; impact if exploited). Controls reference
architecture docs; "V1" = implemented in initial product; "Future" = deferred category.

| ID | Scenario (attack) | Category | Phase | Likelihood | Impact | Controls (V1 unless noted) | Residual risk | Future controls |
|---|---|---|---|---|---|---|---|---|
| T01 | Photo held to camera (mobile/tablet/laptop) | PRES | **V1** | H | H | Device/screen detector; texture/moiré cues; PAD; VLM; burst temporal signals; RETRY/FAIL policy | Medium (depends on threshold; measured per-class APCER) | Better PAD; screen-texture consistency; high-fidelity attack dataset |
| T02 | Printed photo / newspaper / magazine | PRES | **V1** | H | H | Print/print-texture detector; glare/reflection check; PAD; VLM | Medium | Cut-eye/bent-print detection (deferred class) |
| T03 | Static image injected as "camera" (virtual cam/OBS/ManyCam) | INJ | Future | M | H | Capture-time handshake & client integrity signals (future); server-side frame consistency | High today (documented) | Device attestation, stream signing, temporal/motion statistics, virtual-camera heuristics |
| T04 | Replayed video on mobile/laptop screen | PRES/INJ | Future | M | H | V1 temporal burst enables micro-motion signals later; moiré/texture | High today (documented) | Temporal validator (landmark consistency, illumination variation, reflection changes, moiré) |
| T05 | Deepfake / AI-generated face fed to camera or upload | INJ | Future | L-M | H | VLM can flag (POC); no production VLM yet | High today | Dedicated model; provenance; temporal |
| T06 | High-res OLED / curved / partial masks | PRES | Future | M | H | — | High today | Specific detectors (deferred) |
| T07 | Session token stolen/reused (URL/leak/replay) | API | **V1** | M | H | Opaque tokens; short expiry; single-use capture; rate limits; no PII in URL; replay detection events | Low-Medium | Token binding to device/session context |
| T08 | Attacker creates sessions directly (bypass bank) | API | **V1** | M | H | S2S-only session creation with bank client credentials; allow-list; audit | Low | mTLS; nonce/signature |
| T09 | Redirect manipulation (bank return URL spoofed / open redirect) | API | **V1** | M | M-H | Redirect allow-list; state param; opaque result code (no `is_live` in URL); CSP | Low-Medium | Signed return token |
| T10 | Forged/malicious callback to bank claiming PASS | API | **V1** | M | H | Callback only from LivePhoto with signing/credentials; bank verifies via result API; idempotency keys | Low | Mutual TLS |
| T11 | Upload forgery (replay a previous capture's bytes) | API | **V1** | M | H | Single-use session; frame count/recency checks; server-side validation of all frames; session binding; hash integrity | Medium | Temporal liveness on frames |
| T12 | Browser tampering / fake client signals | CLIENT | **V1** | H | M | Client signals are never authoritative; server validates images; reason codes not spoofable | Medium (design limits blast radius) | Attestation (deferred) |
| T13 | Token leakage via logs/referrer | API/CLIENT | **V1** | L-M | H | No tokens in logs; Referrer-Policy; CSP; short expiry | Low | |
| T14 | PII leakage (URLs, logs, errors) | OPS/PRIV | **V1** | L | H | Opaque IDs in URLs; structured redaction; no PII in logs; data-classification rules | Low | Automated secret/PII scanning in CI |
| T15 | Biometric-image leakage (public bucket, mass download) | OPS | **V1** | L | H | Private buckets; signed access only; encryption; least-privilege service accounts; no public URLs; access logging; retention | Low | DLP; egress controls |
| T16 | External VLM provider compromise / data exposure | API/PRIV | **V1 (POC)** | L | H | POC-only approved demo images; never bank test/prod biometrics; egress restriction; contractual review | Low (POC) / n/a (prod) | Remove external dependency in production (self-host) |
| T17 | Rate abuse / credential stuffing on session API | API | **V1** | M | M | Rate limits; request limits; authN at edge; audit events | Low | WAF rules |
| T18 | DoS on capture/upload/VLM | OPS | **V1** | M | M | HPA; resource limits; timeouts; queue caps (later); per-session limits | Medium | Dedicated scaling; CDN/WAF; rate shaping |
| T19 | Model evasion / adversarial image perturbation | API/ML | **V1** | L-M | H | Ensemble evidence (not single model); policy engine; monotonic threshold review | Medium | Attack-specific datasets; robust PAD; periodic red-team |
| T20 | Insider misuse of biometric data / review tooling | OPS | **V1/future** | L | H | Least privilege; role separation; full audit events; no bulk export; reviewer RBAC (M13) | Low-Medium | DLP; periodic access review |
| T21 | Model/prompt/threshold configuration tampering | OPS | **V1** | L | H | Config versioning; code review on config; signed config; audit events on change; immutable model/prompt artifacts | Low | Admin separation of duties |
| T22 | Malformed validator output / model outage → wrong decision | OPS/API | **V1** | M | M-H | Normalized contract; per-validator health; timeouts; fail-safe mapping (no silent PASS); orchestration event | Low-Medium | Circuit breakers; canary model rollout |
| T23 | Session expiry race / browser closes mid-flow | API | **V1** | M | L | Expiry handling; resume/regenerate via bank; idempotent decision | Low | |
| T24 | WebView/rooted/emulator device used with tampered app shell | CLIENT | Future | M | M | Server authority limits damage; no attestation in V1 | Medium today | Device attestation / integrity signals (deferred) |
| T25 | Camera API hooking / stream injection on device | INJ | Future | M | H | — | High today | Attestation + temporal consistency (deferred) |

## 7. Phase separation statement

- **Phase-1 (V1) threats:** T01, T02 (static presentation attacks) are the core PAD target.
  T07–T14, T16(POC), T17, T18, T19, T21, T22 are the security-control targets of the V1
  application/infrastructure.
- **Deferred threats:** T03, T04, T05, T06, T24, T25 and advanced PRES/INJ variants are
  documented, categorised, and reserved in the architecture — but are **not** claimed to be
  mitigated in V1 and must not be reported as if mitigated.

## 8. Top risks (non-technical, must be managed by programme)

1. Absence of a labelled, bank-representative spoof dataset → threshold/calibration done on thin
   data. Mitigation: build evaluation dataset discipline early (M5/M9); report per-attack
   confidence intervals.
2. Silent production dependency on external VLM. Mitigation: `MockVisionProvider` + provider
   abstraction; POC-only gate; self-host path in roadmap (M4→M16+).
3. Metric blindness: aggregate accuracy masking spoof acceptance. Mitigation: APCER/attack-specific
   reporting is a stated product success criterion.
4. Scope creep into identity matching (face↔Aadhaar/PAN). Mitigation: explicit non-scope
   (`PRODUCT_REQUIREMENTS.md` §6).

## 9. Assumptions & notes

- Likelihood ratings are expert judgment for an Indian retail-banking threat environment, to be
  revisited with real telemetry (M14/M15).
- "WebView where feasible" is treated as an equivalent untrusted browser surface (TB-1).
- Threat model must be re-run when: adding active liveness, adding video, moving inference
  on-prem, adding multi-tenancy, or enabling gallery upload.
