# LivePhoto — Camera Compatibility Matrix (M2)

Status: M2 baseline. **All rows are `NOT TESTED` unless a row was actually tested on that
environment.** No physical devices were exercised while authoring this milestone; the automated
suite uses a synthetic camera in Chromium only.

Statuses: `PASS` · `FAIL` · `PARTIAL` · `NOT TESTED`. **Never mark PASS unless it was actually
tested on that environment.** The developer/user populates results after manual device validation.

## How to update

1. Test the M2 capture journey on the environment.
2. Update the matching row(s); add environment/device/OS/browser version in the Notes column.
3. Do not mark an environment PASS based on another environment's result.

## Target matrix

| Environment | camera permission | front camera | rear camera | camera switching | preview orientation | burst capture | retake | background recovery | face detector init | live quality guidance | burst quality evaluation | quality retry | performance observations | notes | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Android Chrome | — | — | — | — | — | — | — | — | — | — | — | — | — | | NOT TESTED |
| Android WebView (where supported) | — | — | — | — | — | — | — | — | — | — | — | — | — | host-app permission policy applies | NOT TESTED |
| iPhone Safari | — | — | — | — | — | — | — | — | — | — | — | — | — | | NOT TESTED |
| iOS WebView (where supported) | — | — | — | — | — | — | — | — | — | — | — | — | — | host-app permission policy applies | NOT TESTED |
| Windows Chrome | — | — | — | — | — | — | — | — | — | — | — | — | — | | NOT TESTED |
| Windows Edge | — | — | — | — | — | — | — | — | — | — | — | — | — | | NOT TESTED |
| macOS Chrome | — | — | — | — | — | — | — | — | — | — | — | — | — | | NOT TESTED |
| macOS Safari | — | — | — | — | — | — | — | — | — | — | — | — | — | | NOT TESTED |
| Chromium (headless, synthetic camera — CI) | PASS | n/a | n/a | n/a | PASS | PASS | PASS | n/a | PASS (stub detector only) | PASS (stub-driven) | PASS (real pixel pipeline on synthetic checkerboard) | PASS | recorded locally, not committed | automated E2E only; synthetic input; stub face provider (M3 §100) | PARTIAL |

> **PARTIAL on the CI row** is intentional: the synthetic-camera Chromium E2E validates the
> software flow and the real pixel-quality pipeline, but it does not prove hardware/camera-driver
> behaviour, real MediaPipe model inference on a device, or iOS/Android/WebView compatibility.

## Notes

- Manual testing instructions live in `docs/CAMERA_CAPTURE_DESIGN.md` §13-14, the M2 milestone
  manual-verification checklist, and `docs/QUALITY_ENGINE_DESIGN.md` (performance/privacy).
- M3-specific rows (face detector init, live guidance, burst quality evaluation, quality retry,
  performance observations) require a real device/camera with the model asset provisioned
  (`frontend/scripts/setup-face-assets.sh`).
- Camera permission, preview mirroring, capture, quality evaluation and background-recovery
  behaviour are verified per environment only with a real device/camera.
- WebView rows depend on the embedding bank application's permission handling.

## M5 update

- **M4/M5 correction:** the earlier synthetic-camera E2E unintentionally fell back to the machine's
  real webcam because `--use-file-for-fake-video-capture` requires `--use-fake-device-for-media-stream`
  to be present. Both flags are now set and the E2E uses a deterministic generated noise fixture.
- **M5 real-provider smoke:** the configured Gemini provider (`gemini-3.8-flash`) returned valid
  structured output on 1-frame and 3-frame synthetic inputs (see `docs/M5_VLM_BASELINE_RESULTS.md`).
  This proves integration, not device or accuracy behaviour.
- Laptop/mobile device rows remain **NOT TESTED** (physical-device testing not performed in this
  environment).