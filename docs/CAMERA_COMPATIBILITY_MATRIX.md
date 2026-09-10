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
- **M5 continuation:** public-dataset purpose corrected to NON_COMMERCIAL_POC_RESEARCH; Axon sample
  bootstrapped (39 samples) and a partial real Gemini baseline measured (3/3 conclusive correct,
  0 spoof→LIVE; free-tier quota exhausted for the remainder — resumable). This is the PUBLIC
  DATASET VLM BASELINE track; it does not validate the LivePhoto capture pipeline.
- Laptop/mobile device rows remain **NOT TESTED** (physical-device testing not performed in this
  environment).

## Pre-M6 update: browser + connectivity preflight

Both capture journeys (`/capture` and `/xbiz/live_photo`) now run a reusable browser/network
preflight gate (`frontend/src/features/connectivity/`) before any camera permission is requested.

**TARGET browser families** (capability-driven, not version lists; no user-agent sniffing, no
polyfills for obsolete browsers):

- current/latest Google Chrome (desktop + Android)
- current/latest Microsoft Edge
- current/latest Firefox
- current/latest Safari (desktop + iOS Safari)

**VALIDATED status:**

- Connectivity preflight has been exercised across Chromium, Firefox and WebKit (automated
  Playwright coverage; camera-free specs pass in all three engines).
- Full camera journey is validated only where tests/devices actually passed. Automated
  camera-dependent coverage is green on Chromium (synthetic camera). Firefox and WebKit
  camera-dependent Playwright coverage remains limited by the test environment (fake-media seams).
- Physical Android Chrome and iPhone/iOS Safari validation is required before any UAT compatibility
  signoff. Firefox/WebKit camera-dependent coverage gaps must not be assumed to be purely Playwright
  test-environment limitations until physical-device validation confirms that.

The gate feature-detects the APIs the current pipeline actually uses
(`window.isSecureContext`, `navigator.mediaDevices.getUserMedia`,
`HTMLCanvasElement.getContext` + `canvas.toBlob`, `Blob`, `URL.createObjectURL` /
`URL.revokeObjectURL`, `window.requestAnimationFrame`). **Backend reachability** is probed via
`GET /api/v1/info` with a short timeout and `cache: 'no-store'`; `navigator.onLine` is only a hint,
the probe is authoritative, and a cached success is never accepted as proof of connectivity.
**Unsupported browsers** see a `Browser not supported` state (or the preserved `INSECURE_CONTEXT`
message) and the camera is never requested. A `browserslist` declaration in
`frontend/package.json` documents the target families.

- **Cold-start offline:** if the LivePhoto URL is opened for the first time while fully offline the
  frontend assets cannot load, so the browser shows its native offline page. Once the app JS has
  loaded, LivePhoto detects connectivity loss and shows its own UI. No service worker/PWA cache is
  introduced in this task (requires a separate security/design decision for this banking flow).

## Pre-M6 update: minimum supported browser version policy

The gate now also enforces a **runtime minimum-version policy** supplied by the backend.

Three DISTINCT concepts — do not conflate them:

| Concept | File / source | Meaning |
|---|---|---|
| `browserslist` (frontend build) | `frontend/package.json` | Frontend **build targeting / documentation** for tooling |
| `browser-support.json` (runtime) | `backend/config/browser-support.json` | **Runtime minimum supported-version policy** served via `/api/v1/info` |
| this compatibility matrix | `docs/CAMERA_COMPATIBILITY_MATRIX.md` | **Evidence / validation record** |

**CONFIGURED MINIMUM (PROVISIONAL — NOT certification claims):**

| Family | minimum_major |
|---|---|
| chrome (desktop) | 120 |
| edge (desktop/Android) | 120 |
| firefox (desktop) | 120 |
| safari (desktop) | 17 |
| ios_safari (Apple/iOS environment) | 17 |
| android_chrome | 120 |

These values are **PROVISIONAL compatibility baselines**, not bank-certified or validated minima.
Final UAT minimum versions MUST be confirmed from the physical/browser compatibility matrix before
signoff.

**TARGET ≠ CONFIGURED MINIMUM ≠ CERTIFIED/VALIDATED:**

- **TARGET** families = the families the product targets (current/latest).
- **CONFIGURED MINIMUM** = the runtime gate values in `browser-support.json` (provisional).
- **CERTIFIED/VALIDATED** = only what has actually been exercised (Chromium synthetic camera today;
  physical Android Chrome / iPhone iOS Safari still required for UAT).

**How an operator changes the policy (no code change):**

1. Edit `backend/config/browser-support.json` (e.g. raise `chrome.minimum_major` above the running
   browser to simulate a block locally).
2. Restart the backend / roll the pod. The policy is loaded **once at application startup**
   (predictable, documented reload semantics — no ad-hoc hot reload).
3. Reload the frontend (or press **Check again**) so a fresh `/api/v1/info` (cache: no-store)
   delivers the new policy.

Later the same JSON can be supplied via a **Kubernetes ConfigMap** mounted at the
`BROWSER_SUPPORT_POLICY_PATH` location without changing application code.

**Validation:** a malformed policy (non-positive minimum, unknown browser key, non-boolean enabled,
missing policy_version) is rejected at startup; the app fails closed in UAT/production (readiness
`unavailable`) and never silently accepts it.

**Security note:** browser/version detection (user-agent based) is a **compatibility /
supportability gate, NOT a security boundary**. It is spoofable and never influences liveness
decisions, PASS authorization, portrait authorization, fraud decisions, or callback security (all
server-authoritative). A supported browser below the configured minimum is HARD BLOCKED with
"Browser update required" (no "Continue anyway"); an unknown family shows "Browser not supported";
a recognized family with an unparseable version is blocked with a "couldn't verify" update message.

**iOS handling:** iOS environments (iPhone/iPad/iPod, including Chrome/Firefox/Edge on iOS) map
conservatively to the `ios_safari` policy using the iOS OS version. They are NOT treated as
equivalent to their desktop engines; Firefox-on-Android and Chromium shells (Samsung/Opera/Vivaldi)
are not in the current policy families and fail closed as "Browser not supported".