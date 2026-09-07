# LivePhoto — Portrait Processing (M5.7)

## Trigger

Experimental VLM `LIVE` only. Other results (`SCREEN_REPLAY`, `PRINT_ATTACK`, `QUALITY_FAILURE`,
`UNCERTAIN`) never run portrait processing.

> **Important semantic boundary:** M5.7 uses experimental VLM `LIVE` only as a temporary trigger
> for testing the portrait-processing pipeline. This does **NOT** establish `VLM LIVE = production
> PASS`. Later, when the authoritative decision engine exists, portrait processing must be triggered
> by the genuine final LIVE/accepted decision. The processor is a narrow service so replacing the
> trigger later does not require rewriting image processing.

## Processor / model

- **Model:** MODNet photographic portrait matting (ONNX), official Apache-2.0 weights from
  `ZHKKKe/MODNet`.
- **Source:** public Hugging Face mirror (`DavG25/modnet-pretrained-models`).
- **Weight version:** `modnet_photographic_portrait_matting.onnx`
- **SHA-256:** `07c308cf0fc7e6e8b2065a12ed7fc07e1de8febb7dc7839d7b7f15dd66584df9`
  (pinned and verified at load via `PORTRAIT_MODEL_SHA256`).
- **Commercial-use status:** Apache-2.0 — permissive (includes commercial use) with attribution.
- **Runtime:** ONNX Runtime (CPU-first); GPU feasible later.
- **Model asset:** provisioned by `backend/scripts/provision-portrait-model.sh` into the
  git-ignored `backend/model-assets/` directory. Never downloaded per-request; never committed.
  A missing/mismatched model is a typed technical error (`PORTRAIT_MODEL_UNAVAILABLE` /
  `PORTRAIT_MODEL_INTEGRITY`), never a silent fallback.

## Matting pipeline

```text
decode selected original (JPEG, untouched)
→ MODNet person matting → soft alpha matte (0..1)
→ conservative edge refinement (light Gaussian on alpha)
→ passport crop (passport-crop-v1)
→ solid background composite
→ high-quality JPEG encode (quality 95)
→ portrait/processed.jpg + portrait/processing.json
```

The matte is **soft** (not binary thresholding): semi-transparent hair edges stay natural. Edge
refinement is conservative to avoid white/black halos and transparent hair holes without
over-smoothing.

## Hair preservation

The passport crop computes a deterministic 3:4 box with a ~10% top margin above the hairline and
head occupying ~60% of the frame height, so head/hair are never clipped and upper shoulders remain
visible. The crop is anchored on the M3 primary face box when provided (never an unrelated face
detector).

## Primary subject rule

The matting model isolates the primary portrait subject. If the capture contains a background
person (distant, peripheral, side/back of head), the matte excludes them and the background
composite removes them — the primary frontal, central subject is retained. Two substantial,
central, participating foreground faces are rejected earlier at capture-quality time
(`MULTIPLE_FACES` via face-participation heuristics in the frontend); a small peripheral face does
**not** force rejection.

## Background replacement

```env
PORTRAIT_BACKGROUND_MODE=solid     # M5.7 supports 'solid' only
PORTRAIT_BACKGROUND_COLOR=#FFFFFF  # validated #RRGGBB
```

Config is validated at startup. No blur/custom scenes.

## Failure handling

Failures become typed technical errors (`PORTRAIT_PROCESSING_FAILED`,
`PORTRAIT_MODEL_UNAVAILABLE`, `PORTRAIT_MODEL_INTEGRITY`, `PORTRAIT_INVALID_SOURCE`). The original
image is **never** returned as a successful processed portrait (no silent fallback). The frontend
shows a customer-safe message ("We couldn't prepare your photo. Please try again."); internal
diagnostics log `transaction_id`, processor/version, error_code, processing_ms — never image bytes.

## Performance

Reported per run: model inference + matting/refinement + crop/composite + encode + total, input and
output dimensions (see `processing.json` and structured logs). No hard production SLA is defined
yet; M5.7 prioritizes correctness/quality.

## Known limitations

- Real hair-quality validation requires a real person/photo (see manual-test section of the M5.7
  report); the development fixture is synthetic.
- Solid background only; background modes are a future seam.
- Crop is deterministic `passport-crop-v1`; reprocessing writes to the same deterministic
  `portrait/processed.jpg` path (idempotent) and records the new processor/config version.