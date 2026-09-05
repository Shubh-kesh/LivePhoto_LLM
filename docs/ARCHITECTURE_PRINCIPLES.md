# LivePhoto — Architecture Principles (M0 Baseline)

Status: M0 baseline. Every downstream design document must be consistent with these principles.
Where a document or a future decision conflicts with a principle, the conflict must be recorded and
resolved explicitly.

---

## P1. Defence in depth

LivePhoto is never `Image -> LLM -> LIVE/SPOOF`. Detection is layered:

```
Captured Frames
      |
      v
Validation Orchestrator
      |
      +--> Face Validator
      +--> Quality Validator
      +--> Device/Screen Validator
      +--> Dedicated PAD Validator
      +--> Vision-Language Model Validator
      +--> Temporal Validator [future]
      |
      v
Validation Results
      |
      v
Scoring Engine
      |
      v
Policy/Decision Engine
      |
      v
PASS / RETRY / REVIEW / FAIL
```

Each validator is independently replaceable, versioned, and observable. See
`VALIDATION_PIPELINE.md`.

## P2. The server is authoritative

The authoritative liveness decision is made and persisted server-side. The browser result is
treated as UX/presentation only. Redirect query strings must never carry `is_live=true` as the
sole proof of success.

## P3. The browser is untrusted

Anything decided only in the client can be manipulated (DevTools, injected JS, virtual cameras,
modified binaries). Client-side validation exists to guide the user and pre-screen, never to
secure. All security-relevant validation runs server-side. Consequences documented in
`THREAT_MODEL.md` and `SECURITY_REQUIREMENTS.md`.

## P4. Models produce evidence, not business decisions

No model output *is* the bank-facing decision. Validators emit a normalized
`ValidationResult`. The scoring engine and policy engine map evidence to
`PASS / RETRY / REVIEW / FAIL`. This keeps any single model's failure from silently becoming a
banking decision.

## P5. Validators are replaceable

Validators conform to one contract (name, version, normalized output, health) and are
registered/configured by name. No business workflow depends on a specific model implementation.
The VLM provider abstraction (`VisionProvider`: Gemini / OpenRouter / Groq / Local / Mock) is an
instance of this principle.

## P6. External AI is an abstraction; production is self-hosted

External VLM providers are permitted **only** for POC/demo scenarios using approved, non-sensitive
images. The production target is a self-hosted model inside bank-controlled infrastructure. The
provider interface must allow switching `external provider -> local/self-hosted provider` without
rewriting business workflows (`ADR-005`).

## P7. Version everything that affects a decision

`application_version`, `validator_version`, `model_version`, `prompt_version`,
`threshold_version`, `policy_version`, `capture_config_version` are recorded against every
decision so that historical outcomes are reproducible. Prompt text is versioned like model weights
(`MODEL_EVALUATION_STRATEGY.md`, §Prompt versioning).

## P8. Privacy by design

Raw biometric frames and final images are **not** logged, not placed in MSSQL business tables,
and not duplicated into observability pipelines. Images live in object storage referenced by
opaque IDs/hashes. Logs carry no PII and no raw biometric data (`DATA_GOVERNANCE.md`,
`OBSERVABILITY_STRATEGY.md`).

## P9. Measurability before optimisation

No tuning happens on intuition. Everything that affects outcomes (validators, models, prompts,
thresholds, capture config) is benchmarked with the methodology in
`MODEL_EVALUATION_STRATEGY.md` before being promoted. Optimise only what is measured.

## P10. Configuration over hardcoding

Policy, thresholds, feature flags, provider selection, frame counts, and retries are externalized
and versioned. Application source must not hardcode policy (`SYSTEM_CONTEXT.md` §Configuration).

## P11. Security ambiguity must not silently PASS

When evidence is insufficient, conflicting, or a validator fails/times out, the system must not
default to PASS. Fail-safe mapping is explicit per component (`VALIDATION_PIPELINE.md`,
`API_CONTRACT.md`): security-critical ambiguity resolves to RETRY / REVIEW / FAIL — never to PASS.

## P12. Distinguish score concepts precisely

The following are **not** interchangeable:

| Concept | Meaning |
|---|---|
| model raw score | model-native output (logit/similarity/…), units vary by model |
| model-generated confidence | whatever the model *claims*; not statistically calibrated by default |
| calibrated probability | transformed score with measured calibration for a defined outcome class |
| decision threshold | versioned operating point applied to a (calibrated) score |
| business risk score | policy-level risk derived from evidence; not equal to any single model score |

LLM-generated confidence must **not** be treated as calibrated probability unless demonstrated by
calibration analysis. See `VALIDATION_PIPELINE.md` §Score semantics.

## P13. Classification over a single undifferentiated SPOOF

Phase-1 attack classes (photo-on-screen, print, newspaper, magazine, blur, multiple faces, no
face, occlusion, low light, tiny face) are separated into deterministic reason codes wherever
technically reasonable. Attack metrics are reported per class.

## P14. Modular monolith first

Day one is a modular architecture, not a microservice zoo. Extract independent processes only when
justified by scaling, GPU needs, a security boundary, deployment independence, or operational
necessity. See `SYSTEM_CONTEXT.md` §Deployment evolution.

## P15. Simplicity, testability, replaceability

Prefer the simple, testable, measurable, replaceable, observable, secure option over
sophistication. Avoid speculative generality.

## P16. Don't over-engineer for scale we don't have

Initial scale is modest (≈20,000 tx/day; ≈180 tx/min peak; ≈5 concurrent captures). Design must
not preclude growth but must not build distributed complexity for it. Inference services are the
one component that must remain independently scalable (`NON_FUNCTIONAL_REQUIREMENTS.md`).

---

## Critical tensions called out (not resolved by fiat)

1. **P11 (fail-closed) vs customer experience.** Aggressive fail-closed raises BPCER (false live
   rejects) and RETRY volume. This is accepted in M0; the operating point is an *empirically
   tuned, versioned* trade-off (M5/M9), never a hardcoded guess.
2. **P6 (self-hosted target) vs M4 (VLM-only baseline on external providers).** The VLM baseline
   will initially run against external POC providers for approved demo data only. This is a *POC*
   result used to decide whether VLM is viable; it must not become a production dependency by
   accident. A `MockVisionProvider` is required so the pipeline is testable offline.
3. **P9 (measurability) vs delivery schedule.** Benchmarks need labelled data; labelled
   spoof data is scarce early. The evaluation framework and synthetic/demo samples must be built
   in M5/M9 before threshold setting, and Phase-1 attack *reporting* is required even when sample
   sizes are small.
4. **Single tenant vs future multi-tenant.** We do not hardcode bank identity in business logic,
   but we also do not build tenant abstractions now. The risk is future refactor; it is accepted
   because speculative tenancy would violate P15.
