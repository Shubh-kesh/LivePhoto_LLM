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

| Environment | camera permission | front camera | rear camera | camera switching | preview orientation | burst capture | retake | background recovery | notes | status |
|---|---|---|---|---|---|---|---|---|---|---|
| Android Chrome | — | — | — | — | — | — | — | — | | NOT TESTED |
| Android WebView (where supported) | — | — | — | — | — | — | — | — | host-app permission policy applies | NOT TESTED |
| iPhone Safari | — | — | — | — | — | — | — | — | | NOT TESTED |
| iOS WebView (where supported) | — | — | — | — | — | — | — | — | host-app permission policy applies | NOT TESTED |
| Windows Chrome | — | — | — | — | — | — | — | — | | NOT TESTED |
| Windows Edge | — | — | — | — | — | — | — | — | | NOT TESTED |
| macOS Chrome | — | — | — | — | — | — | — | — | | NOT TESTED |
| macOS Safari | — | — | — | — | — | — | — | — | | NOT TESTED |
| Chromium (headless, synthetic camera — CI) | PASS | n/a | n/a | n/a | PASS (mirror class present) | PASS (8-frame burst via fake device) | PASS | n/a | automated E2E only; synthetic input, not a physical camera | PARTIAL |

> **PARTIAL on the CI row** is intentional: the synthetic-camera Chromium E2E validates the
> software flow, but it does not prove hardware/camera-driver behaviour, iOS/Android compatibility
> or WebView behaviour.

## Notes

- Manual testing instructions live in `docs/CAMERA_CAPTURE_DESIGN.md` §13-14 and the M2 milestone
  manual-verification checklist.
- Camera permission, preview mirroring and capture are verified per environment only with a real
  device/camera.
- Background-recovery behaviour (visibility change) must be verified on each mobile environment.
- WebView rows depend on the embedding bank application's permission handling.