# LivePhoto — Roadmap (M0 Baseline, updated for M1)

Status: **M0-M4 COMPLETE. M5 ENGINEERING COMPLETE / OVERALL PARTIAL** (real Gemini smoke + partial
public POC baseline; quota-limited remainder resumable; device gates NOT COMPLETE). M6+ are planned
and are **not implemented** in M5. Each milestone: goal / scope / non-scope / dependencies /
deliverables / acceptance criteria / major risks.

Dependencies and acceptance criteria reference the design docs in this repository. Milestones may
be re-sequenced as evaluation results (M4–M9) dictate.

---

## M0 — Product Specification & Threat Model
- **Status: COMPLETE.**
- **Goal:** Authoritative architecture baseline; no code.
- **Scope:** This documentation set (product, principles, context, threat model, pipeline, data
  model, API, evaluation, security, governance, observability, NFR, roadmap, ADRs).
- **Non-scope:** Any implementation, migrations, manifests, models.
- **Dependencies:** None.
- **Deliverables:** All files in this `docs/` tree; M0 completion report.
- **Acceptance criteria:** §67 of the M0 brief (this document set satisfies them).
- **Major risks:** Open stakeholder questions unresolved; thin spoof dataset.

## M1 — Repository Foundation
- **Status: COMPLETE.**
- **Goal:** A clean, runnable skeleton following the M0 contracts.
- **Scope:** Monorepo layout; React+TS+Vite SPA scaffold; FastAPI modular monolith scaffold;
  Pydantic schemas (Zod on client); SQLAlchemy+Alembic foundation; config/versioning plumbing;
  structured logging + request IDs; standard error envelope; health/info endpoints; Prometheus +
  OpenTelemetry hooks; CI lint/typecheck/test; validator and vision-provider seams; developer
  documentation (`docs/DEVELOPMENT_GUIDE.md`). No liveness logic yet.
- **Non-scope:** Camera capture, validation logic, models, deployment.
- **Dependencies:** M0.
- **Deliverables:** Repo skeleton; Alembic initialized (no business migration); domain contracts
  (session state, decision outcome, reason codes, validator result); READMEs; CI workflows.
- **Acceptance criteria:** All checks green (ruff, mypy, pytest ≥80% coverage, ESLint, tsc, vitest,
  vite build); no biometric storage; unit tests require no external network and no MSSQL.
- **Major risks:** Contract drift vs M0; premature microservices (guarded by P14).

## M2 — Secure Camera Capture
- **Status: COMPLETE.**
- **Goal:** Secure, browser-based burst camera acquisition that feeds later quality/liveness
  engines. No liveness detection is performed.
- **Scope:** Secure-context/API checks; explicit permission UX; conservative getUserMedia
  constraints; front/rear switching; live preview with presentation-only mirroring; passive 8-frame
  burst (~1.2 s) with requestVideoFrameCallback + tested rAF fallback; Blob frames; representative
  preview; retake/use-photo; capture-flow state machine; error taxonomy; stream/object-URL cleanup;
  background handling; responsive/accessible UI; unit tests + Playwright fake-camera E2E.
- **Non-scope:** Liveness decisions; PAD; upload endpoints; bank session/token flow; backend capture
  API; persistence; gallery upload; image quality scoring (M3).
- **Dependencies:** M1.
- **Deliverables:** Capture feature (`frontend/src/features/capture/`); fake media test layer;
  Playwright fake-camera E2E; `docs/CAMERA_CAPTURE_DESIGN.md`; `docs/CAMERA_COMPATIBILITY_MATRIX.md`.
- **Acceptance criteria:** No image leaves the browser; no microphone requested; no Base64; no
  persistence; all frontend checks + backend regression green; E2E passes on synthetic camera.
- **Major risks:** Browser/WebView camera quirks; secure-context on mobile.

## M3 — Image Quality Engine
- **Status: COMPLETE.**
- **Goal:** Quality + face validation as first validators.
- **Scope:** Face detection provider abstraction + MediaPipe implementation; live preview quality
  analysis (throttled/backpressured) with customer guidance; per-frame and bundle quality
  assessment; quality-based representative-frame ranking (`frame-ranking-v1`); quality-retry
  flow; normalized pixel metrics (luminance/dark/bright ratio, contrast, Laplacian sharpness);
  deterministic reason codes; provisional quality config (`quality-v1`); model-asset provisioning
  with pinned SHA-256; Playwright E2E with stub face provider + synthetic checkerboard camera.
- **Non-scope:** Attack detection; VLM; decisions beyond RETRY/quality semantics; backend upload.
- **Dependencies:** M2.
- **Deliverables:** `quality/` subsystem; docs (`QUALITY_ENGINE_DESIGN.md`,
  `QUALITY_CONFIGURATION.md`); model-assets provisioning; compatibility matrix update.
- **Acceptance criteria:** All M3 checks green (pixel metrics, face scenarios, bundle ranking,
  guidance, state machine, flow, UI, E2E ready + retry); backend regression green.
- **Major risks:** Thresholds provisional; detector/model unverified on real devices (physical
  gate required before meaningful M4 accuracy).

## M4 — VLM-Only Baseline (Experiment A)
- **Status: COMPLETE (engineering).** Accuracy conclusions pending the real-device gate + a
  meaningful genuine/spoof dataset.
- **Goal:** Stand up VLM-only pipeline on external POC providers.
- **Scope:** `VisionProvider` contract (info/capabilities/evaluate/health); Gemini/OpenRouter/Groq/
  Mock providers; `vlm-passive-v1` prompt + `vlm-result-v1` schema; development-only bounded
  multipart experiment endpoint (disabled by default, refused in uat/production); frame strategies
  `single-quality-v1` and `temporal-triad-v1`; dataset manifest/harness + CLI runner with resume,
  metrics, false-accept/false-reject/disagreement reports; dev experiment UI; E2E with mock
  backend/provider; external-provider policy docs.
- **Non-scope:** Production VLM dependency; bank data; fusion; ensemble decisions; CV spoof layers;
  active liveness.
- **Dependencies:** M3 (including pinned face-model hash + real-model smoke).
- **Deliverables:** Provider package, experiment service/endpoint, harness, docs
  (`VLM_EXTERNAL_PROVIDER_POLICY.md`, `VLM_PROVIDER_ARCHITECTURE.md`, `VLM_PROMPT_DESIGN.md`,
  `VLM_BASELINE_EVALUATION.md`), E2E.
- **Acceptance criteria:** M4 §171 engineering list; all checks green with no provider keys in CI;
  E2E mock flow passes.
- **Major risks:** No live providers exercised; no real-device accuracy; dataset not yet collected.

## M5 — Baseline Evaluation
- **Status: ENGINEERING COMPLETE; OVERALL PARTIAL** (real Gemini smoke + partial public-dataset
  baseline; dataset purpose corrected to NON_COMMERCIAL_POC_RESEARCH; quota-limited remainder
  resumable; device gates NOT COMPLETE).
- **Goal:** Real VLM baseline + failure analysis.
- **Scope:** M4 regression; fake-camera correction verified; artifact audit; dataset licensing
  reassessed under NON_COMMERCIAL_POC_RESEARCH (Axon selected, CC BY-NC 4.0); bootstrap/sampling/
  splits/label-mapping/frame-extraction/validation tooling; runner guards (dry-run, live opt-in,
  max-requests), resume semantics (skips completed, re-runs errored, preserves successes), run
  metadata, Wilson-CI metrics, high-confidence errors, paired strategy comparison, repeatability,
  prompt-injection subset, M6 priority analysis; real Gemini smoke + partial public baseline;
  docs.
- **Non-scope:** M6 detectors; ensembles; bank decisions; active liveness.
- **Dependencies:** M4.
- **Deliverables:** `datasets/` package, `validate_dataset` CLI, metrics/report extensions,
  `docs/M5_DATASET_BOOTSTRAP.md`, `docs/M5_VLM_BASELINE_RESULTS.md`.
- **Acceptance criteria:** M5 §110 — engineering complete; provider gate complete; dataset gate
  complete (POC purpose); accuracy baseline PARTIAL (quota-limited, resumable); device gates
  NOT COMPLETE.
- **Major risks:** Gemini free-tier daily quota; physical device availability.

## M6 — Screen/Device/Print Detection
- **Goal:** Detect Phase-1 static presentation attacks.
- **Scope:** Device/screen-texture/moiré detection; print/newspaper/magazine detection; map to
  SCREEN_REPLAY_SUSPECTED / PRINT_ATTACK_SUSPECTED.
- **Non-scope:** Video/masks (deferred); production self-host.
- **Dependencies:** M3.
- **Deliverables:** Device + print validators; Experiment B progress.
- **Acceptance criteria:** Per-medium detection metrics.
- **Major risks:** High-quality screens; environment variety.

## M7 — Dedicated PAD
- **Goal:** Add a dedicated presentation-attack detection model.
- **Scope:** PAD model selection via benchmark (not assumed); PASSIVE_PAD_FAILED signal.
- **Non-scope:** Advanced/deferred attack classes.
- **Dependencies:** M5/M6 benchmark evidence.
- **Deliverables:** PAD validator; selection benchmark.
- **Acceptance criteria:** PAD model chosen by evidence; per-class APCER improved.
- **Major risks:** Unseen attack classes; dataset scarcity.

## M8 — Ensemble Decision Engine
- **Goal:** Compare and select fusion of A + B (Experiment C).
- **Scope:** Scoring engine; policy engine; fusion candidates (hard rules, weighted, logistic
  calibration, stacked, risk policy, attack overrides); optional parallelization of validators;
  fail-safe mapping; PASS/RETRY/REVIEW/FAIL.
- **Non-scope:** Final production thresholds (M9).
- **Dependencies:** M6/M7.
- **Deliverables:** Experiment C results; policy/decision engine; parallelization decision.
- **Acceptance criteria:** Fusion chosen empirically; no silent PASS.
- **Major risks:** Overfitting fusion to small data; latency of parallel fan-out.

## M9 — Evaluation & Calibration Framework
- **Goal:** Production-grade measurement + calibration.
- **Scope:** Calibration analysis (VLM + CV/PAD); threshold/DET analysis; versioned threshold and
  policy sets; benchmark report automation; false-spoof-acceptance and false-rejection
  investigation tooling.
- **Non-scope:** Dashboard (M15).
- **Dependencies:** M8.
- **Deliverables:** Calibration + threshold selection; automated benchmark reports.
- **Acceptance criteria:** Thresholds chosen fail-closed; APCER/BPCER trade-off documented.
- **Major risks:** Calibration drift over time; over-tuning.

## M10 — Bank Integration
- **Goal:** Wire the real bank S2S + redirect + result/callback flow.
- **Scope:** Session creation API; redirect allow-list; result API; callback with idempotency and
  retry; correlation IDs; bank auth standard.
- **Non-scope:** Multi-tenant; gallery.
- **Dependencies:** M8/M9 core pipeline.
- **Deliverables:** Integration contract implemented and integration-tested against a bank stub.
- **Acceptance criteria:** Bank can create session and obtain authoritative result; redirect
  carries no decision.
- **Major risks:** Bank auth/callback standards unresolved (open questions).

## M11 — Security Hardening
- **Goal:** Close V1 security controls.
- **Scope:** CSP/CORS/CSRF/clickjacking/redirect allow-listing; rate limits; request limits;
  session/token replay protection; secret management; audit event coverage; SAST/DAST baseline.
- **Non-scope:** Pen test scheduling is infra (M20).
- **Dependencies:** M10.
- **Deliverables:** Hardened app; security test evidence.
- **Acceptance criteria:** V1 threat controls (T07–T22) verified.
- **Major risks:** Residual injection attacks (documented, deferred).

## M12 — Data Governance Implementation
- **Goal:** Enforce the governance model.
- **Scope:** Data-zone separation in automation; retention/lifecycle deletion; object-storage
  controls; no-external-data enforcement; model-improvement approval gate.
- **Non-scope:** Legal sign-off (external).
- **Dependencies:** M10.
- **Deliverables:** Governance enforcement + audit.
- **Acceptance criteria:** No cross-zone leakage; retention configurable/versioned.
- **Major risks:** Bank legal timelines.

## M13 — Manual Review
- **Goal:** REVIEW case workflow.
- **Scope:** Reviewer UI; ReviewCase state flow (APPROVE/REJECT); reviewer RBAC + audit;
  exposure of selected image + validation detail; review metrics.
- **Non-scope:** Auto-decide everything.
- **Dependencies:** M8/M9 decisions + REVIEW.
- **Deliverables:** Review workflow.
- **Acceptance criteria:** Reviewer decisions audited; review-reversal telemetry.
- **Major risks:** Review SLA/staffing (open question).

## M14 — Application Observability
- **Goal:** Implement app + security telemetry.
- **Scope:** Prometheus/OTel; structured logs; traces; alerting; correlation IDs.
- **Non-scope:** ML dashboard (M15).
- **Dependencies:** M11.
- **Deliverables:** Instrumented app; alerts.
- **Acceptance criteria:** Latency/error/security telemetry live; no PII labels.

## M15 — Model/Accuracy Dashboard
- **Goal:** Decision-health dashboards.
- **Scope:** ML + business metrics per `OBSERVABILITY_STRATEGY.md`; model/threshold version
  comparison; drift; near-miss.
- **Non-scope:** None material.
- **Dependencies:** M14.
- **Deliverables:** Dashboards.
- **Acceptance criteria:** PASS/RETRY/REVIEW/FAIL + attack-type + model-version views.

## M16 — Containerization
- **Goal:** Containerize UI + API + inference.
- **Scope:** Dockerfiles; image scanning; base images; resource requests/limits; readiness/
  liveness probes.
- **Non-scope:** K8s (M17).
- **Dependencies:** M14.
- **Deliverables:** Container images + scan results.

## M17 — Kubernetes/GKE
- **Goal:** Deploy on GKE.
- **Scope:** Deployments; services; HPA; PDB; ingress; TLS; secrets; network policies; artifact
  registry; namespace/zone separation.
- **Non-scope:** Terraform (M18) — this milestone may use k8s manifests reviewed for later
  codification.
- **Dependencies:** M16.

## M18 — CI/CD
- **Goal:** Automated build/test/deploy.
- **Scope:** CI pipelines (lint/typecheck/test/SAST/image scan); CD to environments; config
  promotion; **Terraform** IaC for infra where preferred.
- **Non-scope:** None material.
- **Dependencies:** M17.

## M19 — Performance & Load Testing
- **Goal:** Prove scale/latency.
- **Scope:** Load test at 180 tx/min + 20k/day; 5 concurrent captures; latency budget
  verification; bottleneck watch-list; HPA tuning.
- **Non-scope:** Over-engineering for larger load.
- **Dependencies:** M17.

## M20 — Security Testing
- **Goal:** Independent security assurance.
- **Scope:** DAST; VA/PT per bank schedule; dependency/container rescan; threat-model refresh.
- **Non-scope:** Fixing (drives M21).
- **Dependencies:** M17/M18.

## M21 — Production Readiness
- **Goal:** Go-live gate.
- **Scope:** RPO/RTO sign-off; backup/restore test; runbooks; on-call; secrets rotation; final
  compliance confirmations; availability verification.
- **Dependencies:** M19/M20 + stakeholder sign-offs.

## M22 — Advanced Presentation/Digital Attacks
- **Goal:** Add deferred classes.
- **Scope:** Video replay; OLED/high-res; curved/bent prints; cut-eye; partial/3D/silicone masks;
  digital injection signals (virtual camera/OBS etc., as feasible); temporal validator
  (micro-motion, landmark, illumination, reflection, screen-texture, moiré, depth).
- **Non-scope:** Anything still proven infeasible (recorded).
- **Dependencies:** M9 framework.

## M23 — Optional Active Liveness
- **Goal:** Add active challenges only if passive proves insufficient.
- **Scope:** Challenge instructions (blink/head-turn/etc.); reuses session/capture pipeline; keeps
  burst/photo UX.
- **Non-scope:** Forcing active liveness if passive is sufficient.
- **Dependencies:** M22 + decision gate (product/fraud).

---

## Open stakeholder questions (tracked; do not block M1)

1. Production SQL Server deployment model. 2. Exact biometric retention period. 3. RPO/RTO.
4. Bank S2S auth standard. 5. Bank callback auth. 6. Production ingress/WAF standard.
7. Bank-approved object storage. 8. Self-hosted VLM choice + GPU. 9. Manual-review SLA.
10. Supported browser/OS matrix. 11. Bank-test dataset approvals. 12. Regulatory mapping owner.
13. Device-channel posture (BYOD vs bank-owned) for future injection controls.

These are duplicated from `SYSTEM_CONTEXT.md` §7 as the single tracked list.
