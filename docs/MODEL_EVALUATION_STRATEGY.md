# LivePhoto — Model Evaluation Strategy (M0 Baseline)

Status: M0 baseline. This is the **measurement backbone** of the product. No threshold, model,
prompt, or fusion method is accepted on intuition; everything is decided here. Applies to
Experiments A, B, C and to every subsequent model/prompt/threshold change.

---

## 1. Goals

1. Decide whether a VLM-only pipeline is viable (Experiment A) and how it compares to
   traditional CV/PAD (Experiment B) and the ensemble (Experiment C).
2. Select models, thresholds, and fusion empirically with **attack-specific** reporting.
3. Establish a repeatable, leakage-safe benchmark harness that all future versions run against.
4. Make false spoof acceptance the primary number that no aggregate metric is allowed to hide.

## 2. Dataset taxonomy

Conceptual label structure (names refinable; semantics fixed):

```
LIVE

SPOOF_SCREEN_MOBILE
SPOOF_SCREEN_TABLET
SPOOF_SCREEN_LAPTOP

SPOOF_PRINT_PHOTO
SPOOF_NEWSPAPER
SPOOF_MAGAZINE

QUALITY_BLUR
QUALITY_LOW_LIGHT
QUALITY_OCCLUSION
```

Metadata per sample (conceptual): device model, camera (front/rear/webcam), browser, OS, lighting,
screen type, attack medium, distance, resolution, subject reference (anonymised), capture
environment. Privacy-safe by construction: subject references are opaque; no identity attributes
are stored with samples (`DATA_GOVERNANCE.md`).

Phase-1 scope = the classes above. Deferred attack classes are tracked separately and never mixed
into Phase-1 "success" claims.

## 3. Data zones (who may benchmark what)

| Zone | Content | External-VLM use |
|---|---|---|
| POC/demo | Public/open samples; synthetic/demo; developer-created non-sensitive samples | **Allowed** (approved, non-sensitive) |
| Bank testing | Bank-internal genuine + spoof (phone-screen, print, blur, varied skin tones) | **Not allowed** by default; requires explicit approval |
| Production | Live production captures | Never external; self-hosted inference only |

Bank testing data must not be auto-copied into public development environments. Boundaries and
approvals: `DATA_GOVERNANCE.md`.

## 4. Metrics

### 4.1 Core classification metrics
- True Live Accept, False Live Reject, True Spoof Reject, False Spoof Accept.
- Precision, Recall, F1 (where appropriate).
- Confusion matrix.
- Attack-type breakdown, device breakdown, browser breakdown, lighting breakdown.
- Latency distribution, confidence distribution, threshold analysis.

### 4.2 PAD metrics (conceptual, ISO 30107-3-flavoured)
- **APCER** — presentation-attack success rate per attack category (the most security-sensitive
  number). Reported **per attack class**, never only as an average.
- **BPCER** — bona-fide presentation error rate (live users rejected).
- Reporting style is chosen to be compatible with formal PAD testing later; **certification is not
  required in M0.**

### 4.3 The rule about aggregate accuracy
A single overall-accuracy figure must never obscure spoof acceptance. Example recorded in the
acceptance criteria: 9,900 live correct + 99 spoof correct + **1 spoof accepted** still looks like
~99.99% accurate but is one security failure. Every benchmark report must therefore show the
attack-specific false-acceptance matrix (APCER per class) alongside any headline number.

### 4.4 Latency & cost
- Latency distribution (p50/p95/p99) per pipeline and per validator; budget bands per
  `VALIDATION_PIPELINE.md` §13.
- Cost per transaction (external VLM tokens for POC; GPU/infra cost for self-host estimates) —
  needed for the external→self-host decision.

## 5. Experiments

### Experiment A — VLM-only
```
Image/frames -> Vision LLM -> LIVE / SPOOF / QUALITY_FAILURE / UNCERTAIN
```
- Providers (POC): Gemini, Groq-supported vision models, OpenRouter-supported vision models;
  `MockVisionProvider` for offline tests.
- Deliverable: does a VLM-only pipeline reach acceptable per-class APCER/BPCER? Outputs are
  **not** treated as calibrated until calibration analysis (M9).

### Experiment B — Traditional CV/PAD
- Candidate layers (no final selection): face detection/count/bbox/landmarks, blur, lighting/
  exposure, pose, occlusion, digital-device detection, print/replay detection, dedicated PAD
  model.
- Deliverable: standalone CV/PAD performance vs Experiment A on the same split.

### Experiment C — Ensemble
```
VLM-only  vs  CV/PAD-only  vs  VLM + CV/PAD ensemble
```
- Same dataset, same splits, same metrics.
- Fusion candidates to evaluate (no weights fixed in M0): hard security rules, weighted score,
  logistic calibration, stacked classifier, risk policy, attack-specific overrides.

All three experiments run against the same evaluation harness and the same held-out set.

## 6. Threshold evaluation & calibration

- Thresholds are operating points over **calibrated** scores, chosen per class/validator on a
  validation set, then confirmed on a held-out test set. Never set on the test set.
- Calibration: probability/score calibration (e.g., isotonic/logistic) applied to model outputs
  with measured calibration curves; LLM confidence is not assumed calibrated
  (`VALIDATION_PIPELINE.md` §4).
- Threshold analysis: APCER vs BPCER trade-off curves (DET-style) per attack class; operating
  point chosen with bank on the fail-closed side of ambiguity (P11).
- Every threshold/policy is versioned and benchmark-referenced.

## 7. Per-attack analysis & failure investigation

### False spoof acceptance (the critical one)
For every accepted spoof: inspect which validator(s) failed, at what score, on which attack
medium/device/lighting; record as a named finding and feed the improvement loop. If an attack
class has few samples, report the class separately with confidence bounds instead of hiding it.

### False live rejection
For every rejected live user: identify quality/face/lighting cause and device/browser cluster.
Excess rejection on a demographic/device cluster is a product and fairness problem — reported, not
swept under "accuracy".

## 8. Provider comparison

POC compares providers on: per-class APCER, calibration quality, latency, cost, schema adherence,
timeout behaviour. Output feeds the production self-hosted model choice (open question #8) but
does not force it.

## 9. Model/prompt version comparison

- Any new model/prompt/threshold must be benchmarked against the current champion on the same
  harness before promotion.
- Prompt versioning: provider, model, `prompt_id`, `prompt_version`, temperature/settings,
  `schema_version`, timestamp; prompt text lives in config/VCS per security policy. Prompt changes
  are model changes.
- Benchmarks are reproducible from recorded versions (`DATA_MODEL.md`).

## 10. Data leakage prevention (future training)

Once ML training starts, guard against train/test leakage:

- **Subject-disjoint**: no near-identical captures of the same person/session across train and
  test.
- **Device-disjoint / attack-medium-disjoint / environment-disjoint** where practical.
- Never train on samples that appear in the test set (including synthetic near-duplicates).

## 11. Benchmark report template

Required sections per report: overall results; per-attack results (APCER/BPCER/DET); per-device;
per-browser; per-lighting; per-model; latency; false-spoof-acceptance samples; false-rejection
samples; confidence distribution; threshold analysis; config/version fingerprints.

## 12. The development loop (documented, required)

```
Hypothesis
   |
Implement validator
   |
Benchmark (same harness)
   |
Inspect failures (attack-specific)
   |
Identify weakness
   |
Add/change layer
   |
Benchmark again
```

Every iteration must be reproducible and versioned; no ad hoc evals.

## 13. Future training strategy (conceptual)

- Enrich bank-testing dataset under governance; use production de-identified samples only with
  approval; keep data zones separated; maintain disjoint-split discipline; consider synthetic
  attacks for deferred classes. Detailed plan belongs to M7/M9+.