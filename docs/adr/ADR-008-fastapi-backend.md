# ADR-008 — FastAPI Backend

- **Status:** Accepted
- **Date:** M0

## Context
The backend must expose a clean S2S API and a capture API, orchestrate validators, enforce policy,
persist to MSSQL, integrate object storage, and emit structured telemetry — as a modular monolith
first (P14), with independently scalable inference later.

## Decision
Backend is **Python + FastAPI**, with **Pydantic** for schemas/validation, **SQLAlchemy** for ORM,
and **Alembic** for MSSQL migrations. The modular-monolith layout keeps sessions/capture/
orchestrator/scoring/policy/callback/persistence as internal modules that can later be separated
(especially inference) without reworking the API contract.

## Alternatives considered
- **Node/Go backend** — not chosen; the team's ML/Python ecosystem (validators, CV/PAD, VLM SDKs)
  makes Python the pragmatic choice for the inference-heavy workload.
- **Microservices on day one** — rejected (P14): no justification at M0 scale.

## Consequences
- FastAPI provides typed request/response (Pydantic ↔ Zod contract), async support for I/O-bound
  orchestration, and OpenAPI documentation for the bank contract.
- Python packaging/typing discipline is required to keep the monolith modular.

## Future review triggers
- If inference separation (M8/M17) demands a distinct runtime boundary, extract the orchestrator/
  inference service while keeping this API contract stable.