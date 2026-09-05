# LivePhoto — Quality Configuration Register (M3)

Every threshold below is:

| Attribute | Value |
|---|---|
| Status | **PROVISIONAL** (NOT CALIBRATED, NOT BANK-APPROVED) |
| Calibration milestone | **M9** (evaluation-data-driven) |
| Version | `quality-v1` (`QUALITY_CONFIG_VERSION` in `frontend/src/features/capture/quality/config/qualityConfig.ts`) |

Changing any value requires a new `qualityConfigVersion` because normalization and the Laplacian
variance depend on preprocessing (analysis resolution, kernel).

## Analysis

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `analysis.maxAnalysisDimension` | 640 | px | max dimension of the normalized analysis buffer | resolution-independent, fast metrics |
| `analysis.previewAnalysisRateHz` | 3 | Hz | live analysis frequency | lightweight live guidance (M3 §15) |
| `analysis.previewStabilizationCount` | 2 | count | consecutive same-category analyses before guidance changes | flicker reduction (M3 §81) |
| `analysis.readyStabilizationCount` | 2 | count | consecutive acceptable analyses before "Ready to capture" | ready stability (M3 §82) |

## Face

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `face.minDetectionConfidence` | 0.5 | 0..1 | minimum detector confidence to count a face | low-confidence detections are unreliable |
| `face.minFaceCoverage` | 0.08 | ratio | minimum face bounding-box area / frame area | face too small to evaluate (move closer) |
| `face.maxFaceCoverage` | 0.6 | ratio | maximum face bounding-box area / frame area | face too large (move farther) |
| `face.maxCenterOffsetX` | 0.25 | normalized | max |dx| of face center from frame center | centering guidance |
| `face.maxCenterOffsetY` | 0.3 | normalized | max |dy| of face center from frame center | centering guidance |

## Exposure

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `exposure.minMeanLuminance` | 0.25 | 0..1 | lower bound of acceptable mean luminance | underexposure |
| `exposure.maxMeanLuminance` | 0.85 | 0..1 | upper bound of acceptable mean luminance | overexposure |
| `exposure.darkPixelThreshold` | 0.1 | 0..1 | luminance below this counts as "dark" | dark-pixel ratio |
| `exposure.maxDarkPixelRatio` | 0.4 | 0..1 | maximum allowed dark-pixel ratio | underexposure/clipping |
| `exposure.brightPixelThreshold` | 0.9 | 0..1 | luminance above this counts as "bright" | bright-pixel ratio |
| `exposure.maxBrightPixelRatio` | 0.35 | 0..1 | maximum allowed bright-pixel ratio | overexposure/clipping |

## Contrast

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `contrast.minContrast` | 0.08 | luminance std-dev | reference for contrast normalization | low-contrast guidance |

## Sharpness

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `sharpness.blurThreshold` | 100 | Laplacian variance | reference sharpness threshold (0..255-scaled) | blur guidance |
| `sharpness.kernel` | `3x3-laplacian` | — | kernel definition | documented preprocessing (M3 §36) |

## Resolution

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `resolution.minWidth` | 320 | px | minimum acceptable frame width | RESOLUTION_TOO_LOW |
| `resolution.minHeight` | 240 | px | minimum acceptable frame height | RESOLUTION_TOO_LOW |

## Bundle

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `bundle.minimumEligibleFrames` | 3 | count | eligible frames required for QUALITY_READY | burst resilience (M3 §83-84); distinct from M2's 6 successfully-encoded frames |
| `bundle.reasonAggregationMinimum` | 3 | count | frames sharing a hard reason before it is aggregated at bundle level | reason aggregation (M3 §85) |

## Scoring / guidance

| Name | Default | Unit | Meaning | Reason introduced |
|---|---|---|---|---|
| `scoring.overallMode` | `min` | — | overallQualityScore = min of component scores | weakest-dimension approach (M3 §49) |
| `guidance.readyScoreThreshold` | 0.7 | 0..1 | overall score at which live guidance becomes "Ready to capture" | ready semantics (M3 §64-65) |

## Versioning note

`captureConfigVersion` (M2, `capture-v1`) and `qualityConfigVersion` (M3, `quality-v1`) are
independent. Both are recorded in `BundleQualityAssessment` so historical outcomes stay
reproducible (M0 P7).