# LivePhoto Frontend — Engineering Guidance

Durable frontend rules for OpenCode agents. See the repository-root `AGENTS.md` for LivePhoto-wide
rules; this file adds frontend-specific invariants.

## Capture & camera invariants

- **Camera permission is requested only after an explicit user action** (`Open camera`); never
  auto-start the camera.
- **No microphone** is ever requested (`audio: false` everywhere).
- Do not substitute the camera with a gallery/upload unless explicitly requested.
- Front-camera preview may be visually mirrored (CSS), but **stored capture pixels must never be
  mirrored**. Full-frame capture is preserved (no cropping by the UI).
- Clean up streams, `srcObject`, object URLs, canvases and providers on teardown.
- No biometric/capture state is persisted (refresh returns to preparation); no
  `onboarding_seen`-style skip.

## Quality & decisions

- Browser quality checks (face, exposure, eye state) are **preliminary UX/evidence signals**, never
  authoritative LIVE/PASS. The frontend cannot manufacture an authoritative decision.
- Closed-eye evaluation is a frontend-only capture-quality gate (MediaPipe Face Landmarker
  blendshapes); no eye images are sent to the backend.
- The visual face guide is a CSS overlay only; captured pixels remain full-frame.

## Customer-facing language

- Use controlled, safe language (`photo`, `camera`, `face`, `lighting`, `try again`). Never leak
  raw machine/provider error codes, reason codes, DOMException names, or metrics to users.
- Never claim liveness/identity verification in customer copy ("Photo captured successfully" is
  capture-success only).

## Accessibility & layout

- Preserve accessibility (semantic headings/buttons, visible focus, `role=status`/`role=alert`,
  screen-reader labels) and mobile viewport behavior (safe-area insets, `100dvh` + fallback,
  landscape usability, no horizontal scroll).

## Configuration & security

- Never put provider/backend secrets in `VITE_*` variables (they are bundled into the browser).
- Runtime public config goes through `window.__LIVEPHOTO_CONFIG__`
  (`frontend/public/runtime-config.js`); Docker generates it from `LIVEPHOTO_*` env vars.
- Cookies/session API must use the configured credential behavior; never weaken security headers.
- Keep customer copy centralized in `src/features/capture/copy.ts` (localization seam).

## Testing

Discovered commands (run from `frontend/`):

```bash
npm ci                 # when the lockfile changes
npm run lint
npm run format:check
npm run typecheck
npm run test:run       # or: npm run test -- --run
npm run build
npm run test:e2e
```

- Deterministic E2E must use a synthetic camera and stub face/eye providers
  (`VITE_FACE_PROVIDER=stub`, `window.__LIVEPHOTO_FACE_STUB__`,
  `window.__LIVEPHOTO_EYE_STUB__`) — never accidentally a physical webcam.
- MediaPipe model assets are provisioned locally and pinned by SHA-256
  (`scripts/setup-face-assets.sh`); never download weights at runtime or commit them.