# ADR-007 — React SPA Frontend

- **Status:** Accepted
- **Date:** M0

## Context
The capture UI must run in Android/iOS browsers and laptops, guide capture, handle camera
permissions, and provide UX-only screening without ever being authoritative.

## Decision
Frontend is a **React + TypeScript SPA built with Vite**, using React Router for routing,
TanStack Query for server state, and Zod for client-side schema validation (mirroring backend
Pydantic). Client logic is strictly UX/preliminary screening; the server remains authoritative
(P3, ADR-003).

## Alternatives considered
- **Server-rendered multi-page app** — rejected: the capture flow needs rich client interaction
  (camera, live guidance, preview) that fits a SPA better.
- **Plain JS / jQuery** — rejected: weak typing and structure for a security-sensitive flow.

## Consequences
- SPA requires strict CSP, frame-ancestors (clickjacking), and careful token handling
  (`SECURITY_REQUIREMENTS.md`).
- Browser is treated as untrusted regardless of framework (P3).

## Future review triggers
- If a bank WebView policy or device matrix imposes constraints not satisfiable by a SPA, revisit.