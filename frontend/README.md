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
```

## Project boundaries

```
src/
├── app/        application shell: routes, providers, error boundary, query client
├── pages/      route-level pages (Home/Foundation, NotFound)
├── components/ shared components (empty in M1)
├── features/   feature-oriented code (capture/result/review — future milestones)
├── api/        typed HTTP transport/client layer
├── hooks/      shared hooks
├── lib/        small reusable infrastructure (env)
├── schemas/    Zod runtime validation (mirrors backend Pydantic contracts)
├── types/      compile-time types not backed by schemas
└── test/       test setup and utilities
```

## Environment variables

Only frontend-safe values may use `VITE_*` (see `frontend/.env.example`). Never place AI keys,
database passwords, bank secrets or service credentials in frontend environment variables — they
are exposed to any user of the browser.

## Camera note

No camera functionality is implemented in M1 and no camera permission is requested. Camera capture
arrives in M2 (`docs/ROADMAP.md`).
