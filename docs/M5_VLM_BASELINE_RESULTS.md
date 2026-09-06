# LivePhoto — M5 VLM Baseline Results

Status: M5 continuation. **PUBLIC DATASET VLM BASELINE = PARTIAL (measured on 3 conclusive real
samples; remainder resumable).** Purpose: `NON_COMMERCIAL_POC_RESEARCH`.

## Dataset

- **Dataset:** Axon public face-anti-spoofing sample (`AxonData/face-anti-spoofing-dataset`,
  Hugging Face) — license **CC BY-NC 4.0**.
- **License state:** `ALLOWED_FOR_POC` (non-commercial research + external VLM processing for the
  POC; attribution required; **not** for production/commercial use).
- **Composition:** 39 samples — LIVE 24 (native stills), SCREEN_MOBILE 10 (videos), SCREEN_DISPLAY
  5 (videos). PRINT_PHOTO: **0** (no print class in the sample; not fabricated). Development 8 /
  holdout 31 (subject-disjoint). `local-data/vlm-baseline/poc-dataset/manifest.jsonl` carries full
  provenance (`source_dataset`, `source_sample_id`, `source_label`, `canonical_label`, split,
  device classes, `license_status`, `usage_purpose`).
- **Validation:** `dataset_validation.json` — 39 samples, 0 duplicates, 0 missing, 0 invalid,
  0 traversal errors.

## Provider

- **Provider/model:** Gemini `gemini-3.8-flash` (local config; exact model used, not changed).
- **Smoke:** single-frame and triad on synthetic inputs returned valid `vlm-result-v1` structured
  output (~2.6–2.9 s).
- **Real benchmark:** Phase-1 pilot (1 per class) + full single-frame run attempted on all 39
  samples.

## Measured real results (single-frame, `single-quality-v1`)

| Sample | Ground truth | Prediction | Attack medium | Self-reported confidence | Correct |
|---|---|---|---|---|---|
| sample-001 | LIVE | LIVE | NONE | 0.95 | yes |
| sample-004 | SCREEN_DISPLAY | SCREEN_REPLAY | MOBILE_SCREEN | 0.92 | yes |
| sample-005 | SCREEN_MOBILE | SCREEN_REPLAY | UNKNOWN | 0.95 | yes |

- Conclusive real evaluations: **3 / 3 correct**.
- **SPOOF -> LIVE observed: 0 / 2 attack samples** (Wilson 95% CI ≈ [0.000, 0.794] per attack
  class at n=1). **This is a tiny finite set — not a production accuracy claim.**
- Genuine non-accept: 0 / 1 (LIVE).
- Uncertain: 0. Technical provider errors in the measured subset: 0.
- An earlier aggregate run also observed additional correct LIVE and SCREEN_DISPLAY classifications
  (4 successes across 3 LIVE + 1 display) before a resume-overwrite bug; per-sample rows for those
  were lost (bug fixed; merge now preserves completed results across resumes).

## Quota / provider reliability

- Gemini free-tier **daily quota was exhausted** mid-run: the full run hit large-scale
  `PROVIDER_RATE_LIMITED` (429). ~80 real requests were made today across smoke/pilot/full-run
  attempts; the large majority were rate-limited, **not** model misclassifications.
- Rate limiting and provider availability are reported separately from model results (M5 §35, §58).
- **No aggressive retry** was used; `--rps` keeps requests below provider limits.

## Single vs triad

- **Triad (temporal-triad-v1) on real data: NOT MEASURED** (quota; video-derived samples have 3
  deterministic frames ready at `frame-extraction-v1` 25/50/75%).
- Infrastructure verified (synthetic smoke returned valid structured output for 3-frame input).

## Confidence

- `self_reported_confidence` reported as uncalibrated model-provided values (0.92–0.95 on the
  measured set). Confidence buckets / high-confidence-error analysis tooling exists; with only 3
  conclusive samples, no confidence analysis is meaningful yet.

## Latency

- Real single-frame calls on ~1000 px face images: ~10.4–11.0 s per request (bigger than the
  ~2.6 s synthetic smoke; payload-size dependent). End-to-end budget implication: ~10 s VLM
  latency is **INCOMPATIBLE** with the eventual <5 s goal unless latency is reduced (smaller
  frames, faster model, or other strategies) — to be revisited with full results.

## Public-dataset limitations (explicit)

Public PAD images were captured under their own cameras, compression pipelines, attack protocols,
framing, lighting and presentation devices. **M5 results do NOT establish accuracy on the LivePhoto
browser capture pipeline.** These results are the `PUBLIC DATASET VLM BASELINE` track only; the
`LIVEPHOTO NATIVE CAPTURE BASELINE` is NOT MEASURED (device gates open).

## Physical device gates

- Laptop: NOT COMPLETE. Mobile: NOT COMPLETE (no physical devices tested; manual checklist in the
  previous report).

## Resume command (run later when quota is available; completed results are preserved)

```bash
cd backend
VLM_EXPERIMENT_ENABLED=true uv run python -m app.experiments.vlm.run \
  --manifest ../local-data/vlm-baseline/poc-dataset/manifest.jsonl \
  --provider gemini --strategy single-quality-v1 \
  --output ../local-data/vlm-baseline/runs/single \
  --live --max-requests 45 --rps 0.1 \
  --dataset-name axon-face-anti-spoofing-sample
```

The runner skips completed (non-error) samples and re-runs errored ones; multiple sessions/days are
supported. Use `--rerun` only to force re-evaluation. For the triad pass, run the same command with
`--strategy temporal-triad-v1` on the video-based samples manifest.

## Where the data lives

- Dataset + artifacts are under git-ignored `local-data/` (never committed). Full per-class and
  Wilson-interval reporting will populate automatically once the quota-limited remainder completes.