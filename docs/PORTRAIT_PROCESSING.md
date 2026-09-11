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
→ matte integrity gate + region-aware refinement (matte-refinement-v3)
→ conservative edge refinement (light Gaussian on alpha)
→ passport crop (passport-crop-v3)
→ solid background composite
→ high-quality JPEG encode (quality 95)
→ portrait/processed.jpg + portrait/processing.json
```

The matte is **soft** (not binary thresholding): semi-transparent hair edges stay natural. Edge
refinement is conservative to avoid white/black halos and transparent hair holes without
over-smoothing.

## Matte refinement (matte-refinement-v3)

MODNet's soft alpha is ideal around hair and fine contours but can turn *solid* dark clothing into
soft "tear" artifacts when the clothing luminance is close to the background. Refinement
(processor `portrait-processor-v5`) distinguishes fine-edge foreground from solid-body foreground:

- **Primary-person component** — a connected region anchored to the M3 primary-face box is
  retained; disconnected background people/objects (furniture, screens, walls) are removed
  regardless of their alpha.
- **Component-trust guard (pre-M6)** — before any destructive disconnected-component removal, the
  selected primary component must credibly cover the primary face ROI. If it does **not** (e.g. the
  raw matte is fragmented and the component is only part of the face/head), destructive removal is
  **skipped** and the raw matte is preserved — deleting uncertain parts of the primary subject is
  worse than leaving background. Raw-matte integrity is still enforced separately (below).
- **Body/face interior reinforcement** — inside the primary support, at/below the forehead, mid
  alpha is pushed toward solid (0.95) so dark shirts/torsos/shoulders stay opaque against a dark
  background.
- **Hair band preserved** — above the forehead, the original soft MODNet alpha is kept so hair,
  hairline and fine edges remain natural.
- **Far background** — forced transparent; uncertain boundary bands keep soft alpha (no binary
  thresholding of the whole mask).

Numpy-only (no OpenCV/SciPy). Provisional in-code thresholds; calibration may adjust them later.
Metadata records `matte_refinement_version: matte-refinement-v3`.

## Primary-subject matte integrity gate (portrait-matte-integrity-v1)

A technically successful JPEG encode does **not** mean the portrait is visually valid. A confirmed
real failure (720x1280, harsh lighting) showed raw MODNet alpha already fragmented in the primary
face/head region (face/head/left side missing; raw left retention 0.11 vs right 0.34) and
refinement deleting further legitimate subject pixels — a corrupted portrait was promoted.

The processor now runs a deterministic structural gate on the **raw** matte (before destructive
refinement) and again after refinement. It uses the M3 primary face box (geometry guidance only, not
an authorization input). Failures are retryable portrait-quality failures; a corrupted portrait is
never promoted and missing subject pixels are never hallucinated.

**Face box is REQUIRED for customer portrait generation.** The primary normalized box is persisted
with the current capture (`capture/capture.json`, bound to `transaction_id`/`attempt_id`/selected
SHA) by both `/capture` and `/xbiz` at upload time. Portrait processing reads the CURRENT capture's
box (a valid same-request box is a compatibility fallback); a missing/invalid box (non-finite,
negative, zero/oversized, or extending past the frame) fails closed with `PORTRAIT_QUALITY_FAILED`.
A stale box from a previous capture can never be used for a newer capture.

Interpretable metrics (all over the primary face/head ROI): face-foreground retention, expanded-head
retention, left/right retention balance, and primary-component coverage of the face ROI.

Provisional thresholds (deterministic, regression-tested, in `app/portrait/integrity.py`):

| Threshold | Value | Meaning |
|---|---|---|
| `FOREGROUND_THRESHOLD` | 0.50 | alpha >= this counts as foreground |
| `MIN_FACE_RETENTION` | 0.55 | catastrophic hole / half-face missing |
| `MIN_HEAD_RETENTION` | 0.45 | severe head-region loss |
| `MIN_LEFT_RIGHT_BALANCE` | 0.35 | one side of the face/head disappearing |
| `MIN_COMPONENT_FACE_OVERLAP` | 0.55 | primary component fragmented beyond safe use |
| `MAX_REFINEMENT_RETENTION_DROP` | 0.15 | refinement materially damaged the face |
| `MAX_REFINEMENT_BALANCE_DROP` | 0.25 | refinement introduced strong asymmetry |

- **Raw gate** — if the raw matte fails, `PORTRAIT_QUALITY_FAILED` is raised (no fallback can
  authorize a broken raw matte).
- **Refinement protection** — the refined matte must still pass and must not drop retention/balance
  materially; otherwise the raw matte (which passed) is used.
- **Post-refinement validation** — the alpha that reaches crop/composite is always one that passed
  the gate, so only a structurally valid primary-subject matte can produce SUCCESS.
- Soft hair edges alone do **not** fail (soft alpha is below the foreground threshold). Without a
  face box only a degenerate (near-empty) matte is rejected — the strong gate needs the geometry
  guidance, which the frontend supplies.

Safe numeric diagnostics are logged (`raw_face_retention`, `refined_face_retention`,
`head_retention`, `left_right_balance`, `component_face_overlap`, `integrity_result`) — never image
bytes, embeddings, PII or secrets.

## Crop framing (passport-crop-v3)

The portrait crop intentionally preserves breathing room and horizontal balance:

- **Face-centered horizontal balance** — the crop is centered primarily on the primary face
  midline (weighted ~70% face center / ~30% subject-matte center), then the frame is sized and
  placed so the full upper-body silhouette keeps visually balanced left/right margins. Asymmetric
  hair volume, head angle or clothing are not over-corrected; the portrait stays natural.
- **Top margin above the hair** — the crop boundary is placed above the highest visible
  foreground hair region (matte top), never below it, so head/hair is never clipped. Target: head +
  hair occupy ~50–55% of the output height with ~8–12% top margin.
- **Side margins beside the shoulders** — the frame is driven by the shoulder width from the
  matte bounds (~8% lateral breathing room per side, floor ~4%), so both shoulders stay visible and
  evenly framed.
- **Upper shoulders** — the bottom of the frame includes the neck/upper-shoulder line.
- **3:4 output** — deterministic and never stretched; the frame is scaled down to fit the source
  when the source cannot hold the full target frame.

The crop is versioned (`passport-crop-v3`); the overall processor is `portrait-processor-v5` with `matte-refinement-v3` and `portrait-matte-integrity-v1`, and recorded with its
normalized bounds in `portrait/processing.json`.

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
`PORTRAIT_MODEL_UNAVAILABLE`, `PORTRAIT_MODEL_INTEGRITY`, `PORTRAIT_INVALID_SOURCE`,
`PORTRAIT_QUALITY_FAILED`). `PORTRAIT_QUALITY_FAILED` is a retryable **portrait-quality** outcome
(the backend worked; the matte/face geometry is unusable) — not liveness, spoof, fraud or
multiple-faces. It maps to **HTTP 422** (not a generic 500) with code `PORTRAIT_QUALITY_FAILED` and
the customer-safe message "We couldn't prepare this photo clearly. Please try again."; the
transaction is left in its pre-portrait retryable state (never `TECHNICAL_ERROR`), so the user can
Retake. The original image is **never** returned as a successful processed portrait (no silent
fallback). Internal diagnostics log `transaction_id`, processor/version, error_code, processing_ms
and normalized integrity metrics — never image bytes, model internals, PII or secrets.

## Performance

Reported per run: model inference + matting/refinement + crop/composite + encode + total, input and
output dimensions (see `processing.json` and structured logs). No hard production SLA is defined
yet; M5.7 prioritizes correctness/quality.

## Known limitations

- Real hair-quality validation requires a real person/photo (see manual-test section of the M5.7
  report); the development fixture is synthetic.
- Solid background only; background modes are a future seam.
- Crop is deterministic `passport-crop-v3` (processor `portrait-processor-v5`,
  `matte-refinement-v3`, `portrait-matte-integrity-v1`); reprocessing writes to the same
  deterministic `portrait/processed.jpg` path (idempotent) and records the new processor/config
  version.

## Fallback segmentation benchmark (NOT integrated)

An offline benchmark of a potential fallback matting model (BiRefNet, SAM 2.1) exists in
`docs/PORTRAIT_SEGMENTATION_EVALUATION.md` with the harness at
`backend/scripts/evaluate_portrait_segmentation.py`. It is **not** wired into the customer flow and
does not change this pipeline. Any future fallback must reuse the same integrity gate and the same
capture/PASS authorization rules, and must not weaken `PORTRAIT_QUALITY_FAILED`.