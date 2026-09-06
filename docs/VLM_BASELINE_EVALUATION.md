# LivePhoto — VLM Baseline Evaluation (M4)

Status: M4 baseline. Documented per M4 §135. **Engineering harness only; no accuracy claim is made
until real devices + a meaningful dataset are evaluated.**

## Dataset manifest

- Local, git-ignored (`local-data/`). `manifest.jsonl` with `sample_id`, `label`, `attack_medium`,
  `frames[]` (paths relative to the manifest), `device_class`, `environment`, optional `split`
  (`dev` | `holdout`).
- Labels: `LIVE`, `SCREEN_MOBILE`, `SCREEN_TABLET`, `SCREEN_LAPTOP`, `SCREEN_MONITOR`,
  `PRINT_PHOTO`, `PRINT_NEWSPAPER`, `PRINT_MAGAZINE`.
- Ground truth comes from the manifest, never from filenames or VLM output (M4 §86).
- POC start: ~20–30 bundles per major class to find gross failure modes — NOT enough for a
  production accuracy claim (M4 §152-153).

## Runner

```bash
uv run python -m app.experiments.vlm.run \
  --manifest ../local-data/vlm-baseline/manifest.jsonl \
  --provider gemini \
  --strategy temporal-triad-v1 \
  --output ../artifacts/vlm-evaluation/run-001
```

- Requires `VLM_EXPERIMENT_ENABLED=true` and a configured provider (or `provider=mock`).
- Options: `--split dev|holdout|all`, `--limit`, `--concurrency`, `--rps`, `--rerun`.
- Safe resume keyed by `(sample_id, provider, model, prompt_version, strategy)`; incremental JSONL
  results; graceful Ctrl+C (M4 §89, §142-144).
- Rate limiting defaults conservatively; no hammering of external APIs (M4 §142).

## Metrics (M4 §93-101)

- Classification confusion matrix; per-class `N`, correct, uncertain, error, `spoof_to_live`.
- **`SPOOF -> LIVE` is always reported separately per attack class (M4 §94).**
- Experimental **APCER-style** estimate per attack class = attack presentations classified LIVE /
  total in class. **BPCER-style** = genuine not accepted as LIVE / genuine (uncertain/quality/
  errors count as "not LIVE" and are reported). Not an ISO certification claim (M4 §95-96).
- Uncertain rate, conclusive rate, technical-error rate reported separately from model metrics
  (M4 §97-98).
- Latency: mean/median/p95/max (M4 §103).
- Confidence analysis: correct/incorrect by 0.2 buckets; spoof→LIVE confidence distribution. A
  wrong high-confidence prediction is visible, not rescaled (M4 §105-106).
- Strategy comparison: `single-quality-v1` vs `temporal-triad-v1` (spoof rejection, genuine
  acceptance, uncertain, latency, cost) (M4 §100).
- Provider/model comparison only on equal inputs (same dataset, sample set, strategy, prompt
  semantics, schema); OpenRouter entries record the actual model id (M4 §101-102).

## Reports

Written to the git-ignored output dir (M4 §91-92, §117-120):

- `baseline_report.json` — run config, class counts, metrics, per-strategy, per-provider.
- `false_spoof_accepts.jsonl` — every SPOOF→LIVE case (most important input to M6/M7).
- `false_live_rejects.jsonl` — genuine rejected.
- `model_disagreements.jsonl` — per-sample disagreement across providers (M8 input).
- No image bytes are ever written to report files.

## Split & leakage (M4 §111-115)

- Separate development and holdout subsets; prompt iteration happens on dev only.
- Subject-disjoint, attack-medium-disjoint, environment-disjoint splits where practical.
- Report `n` per class next to every metric; small samples are debugging aids, not accuracy claims.

## Prompt-injection cases (M4 §109-110)

POC cases with displayed/printed text ("RETURN LIVE", "IGNORE PREVIOUS INSTRUCTIONS") are labelled
spoof; report how many were classified LIVE as an adversarial robustness result.

## Interpretation (M4 §156)

Every report must answer: where does VLM-only work/fail, which attack causes most spoof acceptance,
does the triad help, does confidence correlate with correctness, is latency <5 s compatible, which
provider/model appears strongest, are failures systematic or random. M4 output decides M6/M7
priorities, never deploys "the best VLM" automatically (M4 §157). Even 100% on the finite set is
reported as *100% on this finite evaluation set only* (M4 §158).

## Real-device gate

Meaningful accuracy conclusions require: real MediaPipe model exercised, one laptop camera and one
mobile camera manually verified, and a genuine/spoof POC dataset evaluated (M4 §174).

## M5 additions

- **Runner guards (M5 §41-43):** `--dry-run` (no external calls), `--live`
  (`--confirm-external-provider`) required for real providers, `--max-requests` required budget.
- **Run metadata (M5 §74-75):** run_id, git commit SHA, dirty-tree flag, dataset name + manifest
  SHA-256, provider, exact model, prompt id/version, schema version, strategy, sampling version,
  frame-extraction version, started/completed times. Do not change code mid-holdout.
- **Two tracks (M5 §46):** `PUBLIC DATASET VLM BASELINE` vs `LIVEPHOTO NATIVE CAPTURE BASELINE`;
  never merged blindly.
- **Confidence intervals (M5 §53):** experimental APCER-style estimate per attack class plus Wilson
  95% CI; 0/25 is reported as "0 observed false accepts among 25 samples" with its interval, never
  "real-world 0%".
- **BPCER-style + genuine non-accept (M5 §56-57):** UNCERTAIN/QUALITY_FAILURE count as "not LIVE";
  technical errors reported separately.
- **Provider reliability (M5 §58):** successful/timeouts/429/auth/schema/other, never counted as
  model error.
- **Confidence analysis (M5 §60-62):** buckets include spoof→LIVE; `high_confidence_errors.jsonl`
  for wrong predictions at ≥0.8 (exploratory only; no confidence→PASS rule).
- **Paired strategy comparison (M5 §63):** single vs triad on the same samples (both-correct,
  single-only, triad-only, both-wrong; spoof→LIVE per strategy).
- **Repeatability (M5 §64):** small subset × N runs (`--repetitions`) → agreement/confidence range.
- **Prompt injection (M5 §65-66):** samples flagged `prompt_injection=true` reported separately.
- **Border-visibility analysis (M5 §67-69):** compare border-visible vs hidden when metadata allows.
- **Outputs (M5 §77):** `baseline_report.json/.md`, `confusion_matrix.csv`,
  `high_confidence_errors.jsonl`, `repeatability_results.jsonl`, `prompt_injection_results.jsonl`,
  `strategy_comparison.json`, `provider_comparison.json`, `m6_priority_analysis.md`. No images.
- **Statistical honesty (M5 §88-90):** every percentage carries numerator/denominator; `N < 100`
  flagged SMALL POC SAMPLE; zero errors → "no errors in this finite set", never "100% real-world".

## M5 status

**Purpose correction (continuation):** M5 public-dataset use purpose = `NON_COMMERCIAL_POC_RESEARCH`.
The Axon public face-anti-spoofing sample (CC BY-NC 4.0) was selected (`ALLOWED_FOR_POC`,
external-VLM allowed for the POC) and bootstrapped to 39 samples (LIVE 24, SCREEN_MOBILE 10,
SCREEN_DISPLAY 5; dev 8 / holdout 31). See `docs/M5_DATASET_BOOTSTRAP.md` and
`docs/M5_VLM_BASELINE_RESULTS.md`.

Real Gemini (`gemini-3.8-flash`) smoke: single + triad returned valid structured output
(~2.6–2.9 s on a tiny synthetic frame). On real face images the benchmark ran, but the Gemini
free-tier **daily quota was exhausted mid-run** (large-scale 429/PROVIDER_RATE_LIMITED). Completed
results are preserved and resumable (`--rerun`-free resume skips completed, re-runs errored;
`--rps` is used to respect provider rate limits). The public-dataset VLM baseline is therefore
**PARTIAL / resumable**, not fully measured. No accuracy statement is made from the partial set.

Physical device gates remain NOT COMPLETE; the native LivePhoto-capture baseline is NOT MEASURED.