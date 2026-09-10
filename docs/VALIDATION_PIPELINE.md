# LivePhoto — Validation Pipeline (M0 Baseline)

Status: M0 baseline. Defines the *conceptual* pipeline: capture → frame handling → validators →
scoring → policy → decision. No implementation is specified here; concrete model selection is
deferred to benchmark-driven milestones (M4–M9).

---

## 1. Pipeline overview

```
capture (burst)
   -> frame screening
   -> frame ranking / best-frame selection
   -> face validation
   -> quality validation
   -> screen/device validation
   -> dedicated PAD
   -> vision-language model (VLM)
   -> [future] temporal signals
   -> fusion / scoring engine
   -> policy / decision engine
   -> PASS | RETRY | REVIEW | FAIL
```

Validators are independent, registered, versioned modules that satisfy one interface
(`ARCHITECTURE_PRINCIPLES.md` P4/P5). They **produce evidence**. The scoring engine and policy
engine produce the decision.

## 2. Conceptual validator interface

```
Validator {
  name: string
  version: string            # semantic version of this validator logic
  model_version?: string     # underlying model artifact version (where applicable)
  threshold_version?: string # operating point applied (may be delegated to config)
  validate(input): ValidationResult
  health(): HealthStatus
}
```

## 3. Normalized `ValidationResult` contract

```json
{
  "validator": "digital_device_detector",
  "result": "PASS",                    // PASS | FAIL | UNCERTAIN | ERROR | SKIPPED
  "raw_score": 0.91,                   // model-native output
  "calibrated_score": 0.87,            // calibrated probability for the validator's declared outcome
  "threshold": 0.80,                   // operating point applied
  "reason_codes": [],                  // deterministic codes only
  "model_version": "model-version",
  "validator_version": "1.2.0",
  "prompt_version": "lp-prompts/device/v3",   // for VLM validators
  "configuration_version": "thr-v12",
  "latency_ms": 120,
  "executed_at": "<ISO-8601>",
  "input_reference": "<opaque id or object key, not raw bytes in logs>"
}
```

Rules:

- `result` is one of a small fixed vocabulary, not free text.
- `reason_codes` come from a fixed registry (§9); natural-language model explanations are never
  treated as deterministic reason codes.
- A validator that times out, crashes, or emits malformed output returns `result=ERROR` (or
  `UNCERTAIN`) with `reason_codes` such as `VALIDATOR_TIMEOUT` / `VALIDATOR_ERROR` — it must not
  fabricate a `PASS`.

## 4. Score semantics (never conflate)

| Term | Definition | Notes |
|---|---|---|
| `raw_score` | Model-native output (logit / similarity / LLM token scores). | Units and meaning vary per model; not directly comparable. |
| model confidence | Whatever the model *claims*. | For LLMs this is **not** calibrated probability by default. |
| `calibrated_score` | Post-hoc transform of `raw_score` onto a probability-like scale for the validator's declared outcome, validated by calibration analysis on held-out data. | Calibration is a separate, versioned step (M9), not assumed. |
| `threshold` | Operating point over `calibrated_score` for this validator, from a versioned threshold set. | May differ by policy/risk context. |
| business `risk_score` | Policy-level risk derived from fused evidence across validators. | Computed by the scoring/policy engine, not by any single model. |

LLM outputs must pass through calibration analysis before their `calibrated_score` is trusted.

## 5. Stage-by-stage specification

### 5.1 Capture (burst)

- **Input:** camera stream on device/browser.
- **Output:** 6–12 frames over ~1–2 s (configurable: `capture_config_version`).
- **Purpose:** produce a short temporal burst rather than one isolated frame. Enables best-frame
  selection, quality redundancy, and (future) temporal liveness signals.
- **Failure modes:** camera permission denied; no stream; frame starvation; too few usable frames.
- **Future candidates for retained frames:** micro-motion, landmark consistency, illumination
  variation, reflection changes, screen-texture consistency, moiré changes, depth consistency.
- **Retention rule:** the burst is *transient* — individual raw frames are generally not the final
  stored image; a small, configurable set is retained for audit/evidence with the rest discarded.

### 5.2 Frame screening & ranking

- **Input:** burst frames.
- **Output:** ranked candidate set; the "best" frame(s) carried forward.
- **Purpose:** cheap rejection of unusable frames (hard blur, empty, double exposure) before
  expensive validation; choose the frame most suitable as the customer photograph.
- **Failure modes:** all frames fail screening → treated as quality failure (`RETRY`-eligible).
- **Metrics:** screening pass rate, frame-quality distribution.

### 5.3 Face validation

- **Input:** candidate frames.
- **Output:** face present/count, bounding box, landmarks, size, pose, occlusion indicators.
- **Purpose:** enforce "exactly one adequately sized, reasonably frontal face". Detects
  `NO_FACE`, `MULTIPLE_FACES`, `FACE_TOO_SMALL`, `FACE_OCCLUDED`, extreme pose.
- **Failure modes:** detector errors, occlusion false positives across skin tones (must be
  benchmarked for bias).
- **Future candidates:** improved detector selected by benchmark, not by assumption.

### 5.4 Quality validation

- **Input:** candidate frames.
- **Output:** blur, exposure, contrast, noise, resolution adequacy.
- **Purpose:** reject captures that cannot support a reliable liveness decision
  (`BLURRED`, `UNDEREXPOSED`, `OVEREXPOSED`, `IMAGE_QUALITY_FAILED`) → RETRY.
- **Failure modes:** lighting variance across Indian environments; phone vs laptop cameras.

### 5.5 Screen/device validation

- **Input:** candidate frames.
- **Output:** digital-device / screen-texture / moiré indicators; print indicators.
- **Purpose:** primary detector for T01/T02 (photo on phone/tablet/laptop/monitor) →
  `SCREEN_REPLAY_SUSPECTED`, `PRINT_ATTACK_SUSPECTED`.
- **Failure modes:** high-quality OLED screens, curved prints (future classes).

### 5.6 Dedicated PAD

- **Input:** frames (single and burst).
- **Output:** PAD/presentation-attack score.
- **Purpose:** dedicated anti-spoofing signal → `PASSIVE_PAD_FAILED` when below threshold.
- **Failure modes:** unknown/unseen attack classes.
- **Note:** no specific PAD model is selected in M0; selection is benchmark-driven (M7).

### 5.7 VLM validator

- **Input:** selected frame(s) + a **versioned prompt**.
- **Output:** structured assessment `LIVE / SPOOF / QUALITY_FAILURE / UNCERTAIN` + evidence, via
  `VisionProvider` abstraction.
- **Purpose:** provide a semantic, scene-aware second opinion; explicit separation means a VLM
  outage or weakness does not collapse the decision (P11).
- **Providers (POC):** Gemini, Groq-supported vision models, OpenRouter-supported vision models.
  `MockVisionProvider` supports offline testing.
- **Failure modes:** timeout, hallucinated confidence, prompt drift → handled by prompt versioning
  and calibration (M9).
- **Latency:** the largest single stage; drives parallelization decision (M8).

### 5.8 Temporal signals (future, reserved)

Frame-to-frame consistency checks (motion, landmarks, illumination, reflection, screen texture,
moiré, depth) that reuse the burst. **Reserved, not implemented.** They are the natural upgrade
path against T04 (video replay) and support M22/M23.

### 5.9 Scoring / fusion

- **Input:** all `ValidationResult`s.
- **Output:** evidence summary (per-validator calibrated scores, reason codes, agreement matrix).
- **Purpose:** combine evidence into a small set of business-level signals: `liveness_score`,
  `quality_score`, `risk_score`, `fraud_attempt` flag.
- **Failure modes:** naive averaging of unrelated models (explicitly rejected). Fusion methodology
  must be empirically selected (M8): candidates include hard security rules, weighted score,
  logistic calibration, stacked classifier, risk policy, attack-specific overrides.

### 5.10 Policy / decision engine

- **Input:** evidence summary + policy version.
- **Output:** `PASS | RETRY | REVIEW | FAIL` + reason codes.
- **Purpose:** the only component that emits a banking-relevant decision. Thresholds and mapping
  rules are versioned configuration (`policy_version`, `threshold_version`), never source code.
- **Rules of thumb (refined with data):**
  - Strong attack evidence (screen/print/PAD below threshold, multiple serious reason codes) →
    `FAIL`, even if other signals are benign.
  - Quality/face problems (blur, tiny face, occlusion, low light, no face, too few frames) →
    `RETRY` up to configurable max attempts; then REVIEW/FAIL per policy.
  - Conflict or suspicion without decisive evidence → `REVIEW` where business policy permits.
  - Validator timeout/error/UNCERTAIN → **no silent PASS**; map to RETRY/REVIEW/FAIL by policy.

## 6. Decision semantics (authoritative reference)

| Decision | Meaning | Evidence posture | Typical reasons |
|---|---|---|---|
| PASS | Evidence strongly supports genuine live user | Attack validators ≥ thresholds; no unresolved ambiguity; session valid | none / benign codes |
| RETRY | Capture may be valid but not reliably evaluable | Quality/face problems only | `BLURRED`, `UNDEREXPOSED`, `OVEREXPOSED`, `FACE_TOO_SMALL`, `FACE_OCCLUDED`, `NO_FACE`, poor framing |
| REVIEW | Conflicting/suspicious evidence; policy permits manual review | No decisive attack signal, but material uncertainty/conflict | `MODEL_DISAGREEMENT`, `UNCERTAIN_RESULT`, repeated RETRY, borderline scores |
| FAIL | Strong attack/tamper/invalid-session/repeated-prohibited-behaviour evidence | Decisive attack or security signals | `SCREEN_REPLAY_SUSPECTED`, `PRINT_ATTACK_SUSPECTED`, `PASSIVE_PAD_FAILED`, session/token/redirect violations, max retries exceeded with security concern |

PASS never follows from "not obviously a spoof"; it follows from *positive* evidence with no
unresolved ambiguity.

## 7. Fail-safe behaviour

| Failure | Default behaviour | Rationale |
|---|---|---|
| VLM provider timeout / error | Validator = ERROR/UNCERTAIN → no PASS from that signal; decision from policy (normally not PASS unless corroborated strongly) | Fail-closed for security ambiguity |
| PAD model crash | Same as above | — |
| Database unavailable | Decision cannot be durably persisted → do **not** emit authoritative PASS; surface failure to bank (callback/retry later) | No unpersisted authoritative PASS |
| Object storage unavailable | Frames cannot be durably stored → treat capture as failed; no authoritative decision on unstored biometrics | Auditability |
| Callback fails | Retry with backoff + idempotency; bank can pull result via result API | Delivery not assumed |
| Browser closes / session expires | Session marked expired; no decision or failure recorded; bank informed | — |
| Malformed validator output | Validator = ERROR; policy handles | — |
| Model returns UNCERTAIN | No PASS; RETRY/REVIEW/FAIL per policy | — |

Fail-open is **never** the default for security-critical ambiguity. Where fail-open is proposed
for non-security reasons it must be approved explicitly by security and recorded.

## 8. Parallelization

Conceptually the orchestrator can fan out face/quality, device, PAD, and VLM concurrently:

```
                 Face/quality
                     |
frames -> orchestrator +-> Device detector
                     |
                     +-> PAD
                     |
                     +-> VLM
```

Parallelism is a **later** optimisation (M8) to absorb VLM latency; nothing is parallelized in M0
or M1. The validator contract and orchestrator are designed so this can be introduced without
changing validator implementations.

## 9. Reason-code registry (deterministic, versioned)

| Code | Meaning | Typical decision |
|---|---|---|
| `NO_FACE` | No face detected | RETRY/FAIL per policy |
| `MULTIPLE_FACES` | >1 face in frame | RETRY |
| `FACE_TOO_SMALL` | Face below minimum size | RETRY |
| `BLURRED` | Motion/optical blur too high | RETRY |
| `UNDEREXPOSED` / `OVEREXPOSED` | Lighting outside usable range | RETRY |
| `FACE_OCCLUDED` | Strong occlusion | RETRY/REVIEW |
| `FACE_NOT_CENTERED` | Poor framing | RETRY |
| `IMAGE_QUALITY_FAILED` | Generic unusable quality | RETRY |
| `SCREEN_REPLAY_SUSPECTED` | Digital display indicators | FAIL |
| `PRINT_ATTACK_SUSPECTED` | Print/paper indicators | FAIL |
| `PASSIVE_PAD_FAILED` | Dedicated PAD below threshold | FAIL |
| `PAD_SCORE_BELOW_THRESHOLD` | Fine-grained PAD code | FAIL |
| `MODEL_DISAGREEMENT` | Validators conflict materially | REVIEW |
| `UNCERTAIN_RESULT` | Low-confidence evaluation | REVIEW |
| `VALIDATOR_TIMEOUT` / `VALIDATOR_ERROR` | Operational validator failure | RETRY/REVIEW (never PASS alone) |
| `CAPTURE_TOO_FEW_FRAMES` | Insufficient burst frames | RETRY |
| `SESSION_INVALID` / `SESSION_EXPIRED` | Session not usable | FAIL/redirect |
| `TOKEN_REPLAY_DETECTED` | Reuse of single-use token | FAIL + security event |
| `INVALID_REDIRECT` | Return URL outside allow-list | Blocked + security event |
| `RATE_LIMIT_TRIGGERED` | Rate limit exceeded | Blocked |

Code registry is versioned; codes are never invented ad hoc in production code.

## 10. Model disagreement

`VLM says LIVE` + `PAD says SPOOF` + `device detector says SCREEN` is **not** resolved by
averaging unrelated scores. Recorded as `MODEL_DISAGREEMENT` evidence and handled by policy.
Fusion strategies are candidates to be evaluated empirically in M8; M0 deliberately selects none.

## 11. Explainability

- Every non-PASS outcome carries deterministic machine-readable reason codes (§9).
- Review surfaces (M13) show validation results, scores, thresholds, reason codes, versions, and
  the selected image.
- Natural-language model explanations are auxiliary only, never the basis of the decision.

## 12. Versioning applied here

Every decision persists: `application_version`, `capture_config_version`, each
`validator_version`/`model_version`/`prompt_version`, `threshold_version`, `policy_version`.
Prompts are versioned like models (`provider`, `model`, `prompt_id`, `prompt_version`,
sampling settings, `schema_version`, timestamp). Historical reproducibility is a hard requirement
(`ARCHITECTURE_PRINCIPLES.md` P7; `DATA_MODEL.md`).

## 13. Latency budget (capture → decision < 5 s)

| Component | Target | Warning | Failure | Notes |
|---|---|---|---|---|
| Burst capture + client screening | 1100 ms | 1500 ms | 2000 ms | includes the 1–2 s burst window overlap |
| Frame upload | 500 ms | 800 ms | 1200 ms | selected frames only, sized/config bounded |
| Face + quality validation | 200 ms | 350 ms | 600 ms | |
| Screen/device validation | 250 ms | 400 ms | 700 ms | |
| Dedicated PAD | 350 ms | 600 ms | 900 ms | |
| VLM inference | 1200 ms | 2200 ms | 3000 ms (timeout) | largest lever; parallelized in M8 |
| Fusion + policy | 80 ms | 150 ms | 300 ms | |
| Decision persistence (DB/object refs) | 250 ms | 450 ms | 700 ms | |
| Network overhead / TLS | 200 ms | 350 ms | 500 ms | |
| **Total** | **≈ 3.9 s** | **≈ 4.5–4.8 s** | **≥ 5 s hard cap** | SLO p95 < 5 s; target p95 < 4 s |

Bands are conceptual targets to be re-baselined with real measurements (M5/M14/M19). Numbers are
deliberately not "unrealistically strict". VLM timeout must be short enough that a VLM stall cannot
push the end-to-end decision past the cap while preserving fail-safe semantics.

## 14. Single-person enforcement (subject_count) — pre-M6

Final accepted LivePhoto captures must contain exactly **ONE meaningful visible person/face**.

**Layering (defense-in-depth):**

- **Frontend** `MULTIPLE_FACES` local quality check = early UX / cost optimization. It rejects
  obviously multi-person captures before upload and never authorizes anything.
- **Backend** authoritative VLM `subject_count` (ZERO | ONE | MULTIPLE | UNCERTAIN) = mandatory
  enforcement **before** any canonical PASS. Browser-supplied face counts are never trusted.

**Rule (authoritative promotion):** canonical `PASS` is written ONLY when the backend VLM says
`classification == LIVE` **AND** `subject_count == ONE`. Otherwise the outcome is `RETRY` (with
safe reason codes `MULTIPLE_FACES` / `NO_FACE` where applicable) and `portrait_allowed` is false.
`LIVE` + `MULTIPLE` / `ZERO` / `UNCERTAIN` / missing `subject_count` NEVER produces PASS. Missing
data is never defaulted to ONE.

**Why this is needed:** MODNet portrait matting is not person-instance segmentation. When two
people's bodies/shoulders overlap or touch, MODNet can preserve both in the foreground matte.
Without the backend subject gate, a multiple-person capture could reach portrait processing.
`MULTIPLE` is a **capture-quality failure → RETRY**, never a fraud finding.

**Customer surface:** the backend exposes only safe reason codes (`MULTIPLE_FACES`) — never VLM,
Groq, model output, confidence, or prompt. The frontend maps `MULTIPLE_FACES` to
"Make sure only one person is visible. / Move to a place where no one else is in the photo."

**Enforcement points:** `/api/v1/browser/liveness` (canonical decision + portrait gate),
`/api/v1/browser/portrait`, `/api/v1/browser/submit` (via current-PASS binding), and the standalone
`/api/v1/transactions/{id}/portrait` (requires a persisted LIVE + ONE VLM result).
