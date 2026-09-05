# LivePhoto Frontend

React + TypeScript + Vite SPA for the LivePhoto passive liveness platform (M1 foundation).

## Stack

- React 19, TypeScript (strict), Vite
- React Router (routing), TanStack Query (server state), Zod (schema validation)
- Vitest + React Testing Library + jsdom (tests)
- ESLint + Prettier

## Run locally

Requires Node.js 24 LTS (>= 22.12) and npm.

```bash
npm ci
npm run dev
```

The Vite dev server runs on http://localhost:5173 and proxies nothing by default — the app reads
`VITE_API_BASE_URL` (default `http://localhost:8000`). Start the backend first:
`cd ../backend && uv run uvicorn app.main:app --reload`.

## Scripts

```bash
npm run dev          # dev server
npm run build        # typecheck + production build
npm run preview      # preview the production build
npm run lint         # ESLint
npm run format:check # Prettier check
npm run format       # Prettier write
npm run typecheck    # tsc --noEmit
npm run test         # vitest (watch)
npm run test:run     # vitest (single run)
npm run test:e2e     # Playwright Chromium E2E with a synthetic (fake) camera
```

## Project boundaries

```
src/
├── app/        application shell: routes, providers, error boundary, query client
├── pages/      route-level pages (Home/Foundation, NotFound)
├── features/   feature-oriented code (capture/)
│   └── capture/ M2 secure camera capture: components, hooks, media, state, config, types, utils
├── api/        typed HTTP transport/client layer
├── hooks/      shared hooks
├── lib/        small reusable infrastructure (env)
├── schemas/    Zod runtime validation (mirrors backend Pydantic contracts)
├── types/      compile-time types not backed by schemas
└── test/       test setup and utilities
e2e/            Playwright capture-flow tests (fake camera, Chromium only)
```

## Camera capture (M2)

- Visit `/capture`. The camera is only requested after an explicit **Start camera** action.
- Passive 8-frame burst (~1.2 s) using `requestVideoFrameCallback` with a `requestAnimationFrame`
  fallback; frames are Blobs (never Base64) and remain in memory only — nothing is uploaded or
  persisted in M2/M3.
- Design and error mapping: `../docs/CAMERA_CAPTURE_DESIGN.md`.
- Compatibility status (mostly NOT TESTED, honest): `../docs/CAMERA_COMPATIBILITY_MATRIX.md`.
- Chromium E2E uses a synthetic camera and proves the software flow only; physical-device
  validation is out of scope for CI.

## Quality & face acquisition (M3)

- Live quality guidance (~3 Hz, backpressured) + burst quality analysis with deterministic
  quality-based frame selection (`frame-ranking-v1`) and quality-retry flow.
- Pixel metrics and scoring: `../docs/QUALITY_ENGINE_DESIGN.md`; thresholds (all PROVISIONAL):
  `../docs/QUALITY_CONFIGURATION.md`.
- Face detection uses MediaPipe behind a `FaceDetectorProvider`. The model/WASM are provisioned
  locally (not committed): `frontend/scripts/setup-face-assets.sh` + `frontend/model-assets/`.
- E2E uses a stub face provider (`VITE_FACE_PROVIDER=stub`, test builds only) and a generated
  synthetic checkerboard camera fixture — no real faces, no model download in CI.

## Environment variables

Only frontend-safe values may use `VITE_*` (see `frontend/.env.example`). Never place AI keys,
database passwords, bank secrets or service credentials in frontend environment variables — they
are exposed to any user of the browser.
