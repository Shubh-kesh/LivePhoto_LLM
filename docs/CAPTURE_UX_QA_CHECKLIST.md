# LivePhoto — Capture UX QA Checklist (M5.5)

Use this checklist when validating the guided capture experience on real devices. Mark each row
with the environment actually tested (browser + OS + device). Do **not** claim device support from
viewport emulation alone (M5.5 §95, §101).

## Baseline

- Build and run: `cd frontend && npm ci && npm run dev` (or the production build preview).
- A real or emulated camera is available, or set `VITE_FACE_PROVIDER=stub` for a deterministic
  face.

## Journey checks

| # | Check | Expected |
|---|---|---|
| 1 | Open `/capture` (fresh) | Preparation screen first; no camera prompt, no video |
| 2 | Preparation copy | Mask / spectacles / face-visible / lighting instructions present |
| 3 | Preparation animation | Illustration plays; clear static state under reduced motion |
| 4 | Continue | Advances to the camera-permission explanation |
| 5 | Permission explanation | Shows microphone note; only Open camera requests the camera |
| 6 | Open camera | Native browser prompt appears; LivePhoto never shows a fake prompt |
| 7 | Permission granted | Clean transition into live camera (no technical intermediate states) |
| 8 | Guidance | One stabilized instruction; transitions by fade, no flicker |
| 9 | Ready | "Ready to capture" with guide/check; no liveness wording |
| 10 | Capture | Clear shutter; capture disables controls and shows only "Hold still…" |
| 11 | Checking | "Checking photo quality…" — no percentages, no metrics |
| 12 | Preview | M3 quality-selected image; Retake secondary, Use photo primary |
| 13 | Use photo | "Photo captured successfully" + "Your photo is ready." |
| 14 | No liveness claims anywhere | No verified/liveness/you passed/fraud wording |
| 15 | Retake from preview | Returns to camera; a second capture works |

## Quality retry

| # | Check | Expected |
|---|---|---|
| 16 | Trigger a blurry/no-face/underexposed capture | Retry screen with matching customer copy, raw code hidden |
| 17 | Try again | Returns to camera and capture again |
| 18 | Back to start | Returns to preparation; camera fully stopped |

## Errors

| # | Check | Expected |
|---|---|---|
| 19 | Permission denied | "Camera access is blocked" + Allow-in-settings copy; Try again present |
| 20 | Camera busy (another app) | "Camera is being used by another app" |
| 21 | Unsupported browser / no camera | "Camera isn't available in this browser" / "We couldn't find a camera" |
| 22 | Quality internal failure | "Something went wrong while checking your photo" |
| 23 | Technical wording | No DOMException / NotAllowedError text in any error UI |

## Navigation / lifecycle

| # | Check | Expected |
|---|---|---|
| 24 | Back from permission | Returns to preparation |
| 25 | Back from camera | Returns to preparation AND stream stops (camera indicator off) |
| 26 | Refresh mid-flow | Returns to Preparation; no image restored from storage |
| 27 | No persistence | No localStorage/sessionStorage/IndexedDB image or instruction state |
| 28 | Object URLs | No leaked blob URLs (revoked on reset/unmount) |
| 29 | Help during camera | Non-destructive overlay; camera keeps running; Close/Esc returns |
| 30 | Switch camera | Secondary; works only when 2+ cameras; recovers previous on failure |

## Layout / viewport (see also §95 list)

| # | Width x height | Portrait/landscape checks |
|---|---|---|
| 31 | 360 x 800 | No horizontal scroll; controls above safe area; thumb reach |
| 32 | 390 x 844 | Same |
| 33 | 430 x 932 | Same |
| 34 | 768 x 1024 | Centered contained camera card |
| 35 | 1366 x 768 | Contained camera card; no full-monitor stretch |
| 36 | 1440 x 900 | Contained camera card |
| 37 | Mobile landscape | Usable, orientation not forced |
| 38 | Safe areas | Bottom controls clear the home indicator; top bar clear of notch |

## Accessibility

| # | Check | Expected |
|---|---|---|
| 39 | Keyboard | Full journey operable with Tab + Enter; visible focus rings |
| 40 | Screen reader | Headings/buttons labelled; guidance announced as status; errors as alert |
| 41 | Reduced motion | Animation static but understandable; instructions readable |
| 42 | Touch targets | All primary controls >= 48px |
| 43 | Color | Guidance/state never relies on color alone |

## Performance / content

| # | Check | Expected |
|---|---|---|
| 44 | First paint | Preparation shows immediately (no wait for MediaPipe/camera/VLM) |
| 45 | Model load | Face model preload does not block first paint; camera not opened early |
| 46 | Copy length | No instruction becomes a dense paragraph on small screens |

## Manual results log

| Environment tested | Date | Result | Notes |
|---|---|---|---|
| (fill in: browser/OS/device + camera) | | | |

## Closed-eye gate (M5.7)

| # | Check | Expected |
|---|---|---|
| 1 | Eyes open | Frame eligible; capture succeeds |
| 2 | One eye closed (wink) | That frame ineligible; another open-eye frame selected, or retry |
| 3 | Both eyes closed | Retry with "Keep your eyes open and look at the camera." |
| 4 | Normal blink during burst | A blink never fails the whole transaction if another open frame exists |
| 5 | Live preview closed eyes | "Open your eyes and look at the camera." (stabilized, no raw codes) |
| 6 | No closed-eye final frame | A closed-eye frame can never appear as Use photo's image |
| 7 | Background person eyes | Incidental background person's eyes never affect the primary user |
| 8 | In-memory processing | No eye images transmitted; camera privacy unchanged |

## Viewport verification results (automated/screenshot or manual)

| Viewport | Horizontal overflow? | Notes |
|---|---|---|
| 360 x 800 | | |
| 390 x 844 | | |
| 430 x 932 | | |
| 768 x 1024 | | |
| 1366 x 768 | | |
| 1440 x 900 | | |
