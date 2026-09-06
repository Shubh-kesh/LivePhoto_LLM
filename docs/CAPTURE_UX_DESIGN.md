# LivePhoto — M5.5 Capture UX Design

## Purpose

M5.5 transforms the functional capture UI into a polished, trustworthy, banking-grade
face-photo capture experience (the "guided capture journey"), while keeping the M2/M3 capture and
quality engines authoritative and unchanged. This is a UX milestone: no VLM/PAD/quality logic,
no backend changes, no decision/PASS-FAIL semantics were added.

## UX principles

- **Prepare before prompting** — a fresh visit shows preparation first; the camera is never
  requested or opened automatically.
- **Explain before permission** — LivePhoto explains *why* camera access is needed on a dedicated
  screen before invoking `getUserMedia()`. The browser prompt itself remains browser-controlled;
  no fake permission dialog is shown.
- **One instruction at a time** — the capture screen shows a single, calm, stabilized guidance
  message (from M3). No flicker, no jargon.
- **Progress, not pressure** — a subtle three-step indicator (Prepare / Capture / Review) shows
  where the customer is.
- **Trustworthy language** — only capture language ("photo", "camera", "face", "lighting",
  "try again"). No liveness/PAD/AI/MediaPipe/VLM wording. Success is "Photo captured
  successfully" — never "verified" or "passed".
- **Camera-dominant on mobile, contained on desktop**.
- **Privacy by default** — no captured-image or instruction state is ever persisted; refresh
  returns to preparation.

## Journey

```
/capture (fresh visit)
  -> Preparation / Welcome  (animated illustration + checklist)
  -> Continue
  -> Camera permission explanation
  -> Open camera   (the ONLY way getUserMedia is invoked)
  -> Native browser permission
  -> Live camera   (streaming)
  -> Positioning/quality guidance (M3) -> Ready to capture
  -> Capture photo  ->  Hold still…  (invisible ~8-frame burst, unchanged)
  -> Checking photo quality…
      |-> quality retry  -> reason-based customer copy -> Try again
      \-> preview (review) -> Retake  |  Use photo
  -> Photo captured successfully
```

A full reload always returns to Preparation (no persistence, no `onboarding_seen`).

## Screen hierarchy

| Screen | Flow state(s) | Purpose |
|---|---|---|
| `PreparationScreen` | idle + stage=prepare | Welcome, animated instructions, Continue |
| `PermissionScreen` | idle + stage=permission | Camera-access explanation, Open camera |
| `StartingCameraScreen` | requestingPermission | Non-technical pending state while getUserMedia runs |
| `CameraScreen` | streaming / switching / capturing | Live camera, guide, guidance, shutter, help, back |
| `QualityCheckingScreen` | analyzing | Subtle "Checking photo quality…" |
| `QualityRetryScreen` | qualityRetry | Reason-mapped customer copy, Try again |
| `ReviewScreen` | preview | Your photo, Retake (secondary) / Use photo (primary) |
| `SuccessScreen` | confirmed | "Photo captured successfully" |
| `ErrorScreen` | error | Camera/technical vs quality errors, kept separate |
| `HelpSheet` | overlay during streaming | Non-technical help; non-destructive |

The stable `<video>` node is always rendered as the first child of the page and is hidden
(stream still attached) through permission/analysis/retry phases so it survives every transition
(M2 §12, M3 §60). Overlay screens sit above it. This is the key constraint that drove the
`CameraScreen`-first layout.

## State model

The M2/M3 capture-flow state machine remains authoritative (no scattered booleans). Presentation is
derived from `flow.state` plus a small two-step pre-camera `stage` (`prepare` -> `permission`).
Conceptual UX states map cleanly:

`PREPARING` (idle+prepare) → `PERMISSION_EXPLANATION` (idle+permission) →
`REQUESTING_PERMISSION` → `STREAMING` → `CAPTURING` → `ANALYZING` → `QUALITY_RETRY` →
`PREVIEW` → `CONFIRMED`, with `ERROR` for camera/quality failures.

Impossible actions are guarded by the state machine (capture while preparing, use-photo before
preview, open-camera twice, retake while capturing). Back navigation:

- permission → preparation (nothing to clean up — camera not started)
- camera (streaming/capturing/analysis/retry) → preparation via `flow.reset()`, which stops the
  stream and revokes object URLs
- review → retake reacquires the camera through the existing flow
- success → start over returns to preparation

## Copy

All customer-facing copy is centralized in `src/features/capture/copy.ts` under a nested
`captureCopy` object (e.g. `captureCopy.prepare.title`, `captureCopy.permission.title`,
`captureCopy.camera.ready`). This is the future localization seam: a future i18n pass can replace
the object without touching components.

Quality reason codes (`NO_FACE`, `UNDEREXPOSED`, `BLURRED`, …) are mapped to customer action copy
by `retryCopyForReasonCodes`; raw codes are never rendered. Flow errors are mapped to customer
copy by `errorCopyFor`, which keeps camera failures ("Camera access is blocked", "Camera is being
used by another app", "Camera isn't available in this browser") visually and semantically separate
from quality failures ("Something went wrong while checking your photo"). DOMException names are
never shown.

## Progress model

`ProgressSteps` shows Prepare / Capture / Review. During camera the step is implied by a small
top-bar chip. "Review complete" is never shown before Use photo.

## Design tokens / theme

CSS custom properties live in `src/design-system/tokens.css` (color, spacing, radius, typography,
shadow, focus, breakpoints, safe areas, motion). The default theme is a restrained premium
banking/KYC look: light neutral background, white surfaces, high-contrast text, a single blue
accent (`--lp-color-primary`), subtle shadows, medium radius, generous whitespace, system font
stack. No gradients-as-decoration, no glassmorphism, no external fonts/illustrations.

A small component set lives in `src/design-system/`: `Button`, `IconButton`, `ProgressSteps`,
`StatusMessage`, `ScreenLayout`, `Card`, `LoadingIndicator`, `BrandHeader`, plus local SVG icons
(camera, camera-switch, mask, spectacles, lighting, check, warning, back, help). Local
illustrations are hand-written SVG/CSS — nothing is hotlinked.

## Responsive behavior

- **Mobile-first** (target 360–430 px). The camera screen is full-bleed and camera-dominant;
  controls sit above `env(safe-area-inset-bottom)`; the top bar respects `env(safe-area-inset-top)`.
- The page root uses `100dvh` with a `100vh` fallback.
- **Landscape**: never forced; camera controls compact and usable at short heights.
- **Desktop** (>= 40rem): the capture surface is a centered, contained card (max-width 560px,
  3:4), surrounded by the neutral page background — never a stretched webcam across the monitor.
- No horizontal scrolling at any supported width.

## Animation

- **Preparation illustration** (`InstructionAnimation`): an original, non-photorealistic SVG. A
  12 s CSS cycle shows (1) a mask fading in and away, (2) spectacles fading in and away, and (3)
  the face sliding into the guide with a check. Local SVG + CSS only, no framework, no network
  assets.
- **Screen/guidance transitions**: subtle fade/slide. Guidance message keys re-trigger a gentle
  in-animation. Capture→Checking is continuous (the camera dims behind the checking screen — no
  white flash).
- **Quality checking**: a subtle spinner; no fake percentages.
- All animations respect `prefers-reduced-motion`; the illustration degrades to its clear final
  state and the instruction list always carries the content, so animation is never required to
  understand the guidance.

## Face guide / guidance

The existing M3 face guide and guidance stabilization are reused. The guide is a pure CSS overlay
(no crop — full-frame pixels are preserved for future spoof analysis) with three visual states:
`neutral`, `needs_attention`, `ready`. Never `spoof`/`fraud`/`live`. Readability over any camera
background is ensured by a scrim pill behind the single guidance message; text is never the only
signal (guide state + check icon accompany it).

## Error UX

- **Quality retry** = "Let's try again" + reason-based customer instruction (blurred → hold
  steady; under-exposed → brighter place; etc.).
- **Camera/technical failures** get their own screen: blocked permission, camera in use, no
  camera, unsupported browser, secure context, generic start failure, quality-analysis internal
  error. Each has its own friendly copy and a Try again / Back to start pair.

## Accessibility

Semantic headings, real buttons, visible focus (`:focus-visible` ring), screen-reader labels on
icon buttons, `role="status"` for live guidance and `role="alert"` for errors/retry. Touch targets
>= 48px. `prefers-reduced-motion` honored. Color is never the only meaning (icons + text +
state).

## Experiment / debug separation

The customer path `/capture` renders no experiment/debug UI. The VLM experiment panel lives only
on the explicit development route `/dev/vlm-experiment` (rendered behind `import.meta.env.DEV`);
it is never part of the normal flow.

## Future bank branding

Theming and branding are centralized so a bank can supply `brand_name`, `logo_url`/approved asset,
and `primary_color` without touching capture/security logic. `BrandHeader` accepts a future brand
name/logo; tokens are semantic. See `docs/BRANDING_INTEGRATION.md`. No remote dynamic theming is
implemented.

## Security invariants preserved

- Microphone is never requested (`audio: false` everywhere; unchanged).
- Security headers (CSP, `frame-ancestors 'none'`, `Permissions-Policy: camera=(self)`) unchanged.
- Full-frame capture pixels unchanged; mirroring remains preview-only (front mirrored, rear not).
- Stream/object-URL cleanup and no-persistence behavior unchanged and covered by tests.
