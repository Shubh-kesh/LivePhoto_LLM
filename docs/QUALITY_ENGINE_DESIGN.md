# LivePhoto — Quality Engine Design (M3)

Status: M3 baseline. Client-side preliminary quality and face-acquisition engine.

## Purpose

Evaluate whether captured camera frames are **technically suitable** for later liveness/spoof
analysis:

- face presence, count, size, position, detection confidence
- blur/sharpness, brightness, underexposure, overexposure, contrast, image dimensions

Outputs drive live capture guidance, per-frame and per-bundle quality assessment, quality-based
representative-frame selection, and quality-retry requests.

## Non-purpose (critical boundary)

M3 does **not** answer "is this human live?" (M3 §2). "Face detected / good lighting / sharp /
well-centered" are **not** liveness evidence — a photograph on a phone can satisfy every M3 rule.
The UI only ever shows capture-quality language, never "Live person detected", "Verified",
"Spoof check passed", etc. MediaPipe Face Detector is not a liveness/spoof detector; its
confidence must never populate `liveness_score`, `spoof_probability`, or `risk_score` (M3 §10).

## Quality pipeline (M3 §5)

```
Camera preview -> live quality analysis (throttled, backpressured) -> customer guidance
Capture 8-frame burst -> analyze EVERY frame -> FrameQualityAssessment[]
   -> BundleQualityAssessment -> select representative (quality-based) -> PREVIEW | QUALITY_RETRY
```

## Face detector (M3 §8-10, §72-75)

- `FaceDetectorProvider` interface; `MediaPipeFaceDetector` implementation behind it. Capture
  logic depends only on the interface (swap-in for YuNet/RetinaFace/custom later).
- Model/WASM assets are served from the LivePhoto-controlled origin
  (`frontend/model-assets/`, `frontend/public/mediapipe-wasm/`); see
  `frontend/model-assets/README.md` and `scripts/setup-face-assets.sh` (pinned SHA-256).
- One detector instance per capture session; `initialize()` explicit; dispose on teardown.
- Detector failure → `FACE_ANALYSIS_UNAVAILABLE`, never `NO_FACE`. Analysis failure →
  `QUALITY_ANALYSIS_ERROR`, never an image-quality classification (M3 §114-115).

## Metric formulas (M3 §28-37)

All pixel metrics run on a **normalized analysis buffer**: preserve aspect ratio, max dimension
~640 px (configurable), grayscale via the documented Rec. 709 formula
`Y = 0.2126 R + 0.7152 G + 0.0722 B` normalized to 0..1. Original `CaptureFrame.blob`s are never
modified.

| Metric | Formula | Units |
|---|---|---|
| `meanLuminance` | mean of grayscale buffer | 0..1 |
| `darkPixelRatio` | fraction of pixels `< darkPixelThreshold` (0.1) | 0..1 |
| `brightPixelRatio` | fraction of pixels `> brightPixelThreshold` (0.9) | 0..1 |
| `contrast` | luminance standard deviation | 0..1 (raw) |
| `sharpness` | variance of the Laplacian (3x3 kernel) over the buffer, computed on 0..255-scaled luminance | raw (higher = sharper) |
| `faceCoverageRatio` | normalized face bounding-box area / frame area | 0..1 |
| `centerOffset` | normalized face-center offset `(dx, dy)` with `distance = sqrt(dx²+dy²)` | normalized |

Sharpness is only comparable for the SAME preprocessing configuration; config changes require a
new `qualityConfigVersion` (M3 §36).

## Normalization (M3 §50)

Deterministic, unit-tested, bounded 0..1. `normalized_score` is **not** a calibrated probability
(M3 §42). Functions: `normalizeExposure`, `normalizeContrast`, `normalizeSharpness`,
`normalizeFace` (see `quality/engine/qualityEngine.ts`).

## Quality scoring (M3 §48-49)

`overallQualityScore = min(exposure, contrast, sharpness[, face])` — the "weakest quality
dimension" approach, PROVISIONAL. It is an interpretable 0..1 quality indicator, explicitly NOT a
probability, NOT liveness confidence, NOT spoof probability.

## Hard vs soft rules (M3 §47)

Hard blockers disqualify a frame: `NO_FACE`, `MULTIPLE_FACES`, `FACE_TOO_SMALL`, `FACE_TOO_LARGE`,
`BLURRED`, `UNDEREXPOSED`, `OVEREXPOSED`, `LOW_CONTRAST`, `RESOLUTION_TOO_LOW`, plus
`FACE_ANALYSIS_UNAVAILABLE` / `QUALITY_ANALYSIS_ERROR` for failures. `FACE_OFF_CENTER` is a soft
warning (guidance) that reduces score but does not disqualify.

## Frame ranking (M3 §56-58)

`frame-ranking-v1`, from eligible frames only: overallQuality → detection confidence → center
proximity → temporal-center tie-break → earliest sequence. Deterministic, no ML.

## Bundle rules (M3 §51-55, §83-85)

- Analyze every burst frame; decode one at a time, release the bitmap immediately.
- `eligibleFrameIds` = frames with no hard blockers; QUALITY_READY requires `>= minimumEligibleFrames`
  (provisional default 3) — distinct from M2's `minimum successful encoded frames` (6).
- Reason aggregation: a hard reason is reported at bundle level when it appears in `>=`
  `reasonAggregationMinimum` frames (3); if no eligible frames and no common reason, fall back to
  the most frequent reason so retry guidance is never empty.
- Non-selected frames are NOT discarded (M4+ validators may need them); only temporary decode
  buffers are released.
- Dispositions: `QUALITY_READY` / `QUALITY_RETRY` / `ANALYSIS_UNAVAILABLE` — deliberately distinct
  from the liveness PASS/FAIL vocabulary (M3 §46).

## Live guidance (M3 §62-65, §81-82)

Priority-ordered single message (never ten warnings): NO_FACE → MULTIPLE_FACES → FACE_TOO_SMALL/
FACE_TOO_LARGE → exposure → blur → centering → low contrast → READY/NEUTRAL. Guidance changes only
after the same category is observed for `previewStabilizationCount` consecutive analyses (2).
"Ready to capture" means current preview quality appears suitable — NOT liveness verified.
Auto-capture is intentionally not implemented (M3 §66); the Capture button is never hard-blocked
by a single noisy live analysis (M3 §67).

## Performance (M3 §15-18, §119-120)

- Live analysis throttled at ~3 Hz with strict backpressure: one analysis at a time, latest-frame-
  wins, skip when busy — never an unbounded queue.
- If analysis becomes slow, reduce frequency rather than queue. Web Worker migration is documented
  as a future option if real measurements justify it.
- Local dev-only diagnostics record `camera_start_ms`, `burst_duration_ms`,
  `total_capture_flow_ms`, per-frame `analysisTimeMs`, bundle `totalAnalysisTimeMs`, and per-frame
  metric values (M3 §70, §86).
- UX target: burst → quality result/preview comfortably below one second where practical. This is
  a development target, not a contractual NFR; the final <5 s budget includes quality + VLM/PAD +
  decision (`VALIDATION_PIPELINE.md`).

## Privacy (M3 §87-88, §112)

- Quality results stay in application memory; nothing is written to localStorage/sessionStorage/
  IndexedDB/cookies/analytics.
- No image data, blobs, Base64, object URLs, canvas pixel data, device IDs, or raw biometric
  analytics are logged. Diagnostics show metrics only.
- No gallery upload, no external AI, no fingerprinting.

## Limitations

- Thresholds are PROVISIONAL / NOT CALIBRATED / NOT BANK-APPROVED (see
  `docs/QUALITY_CONFIGURATION.md`); M9 calibrates them.
- Face centering is not head pose; occlusion is not robustly detected (M3 §26-27).
- No moiré/screen/print/PAD, no depth, no rPPG, no texture anti-spoof, no face matching, no
  demographic inference (M3 §121-123).
- Detector/model behavior is unverified on real devices until the physical-device gate is met.

## Future backend validation

The browser is untrusted; M3 results are preliminary UX/evidence only (M3 §6). The architecture
keeps metric computations in pure functions so the same quality checks can be repeated on the
backend in later milestones without re-deriving formulas.