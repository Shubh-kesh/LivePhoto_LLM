# Architectural Decision Records (ADR)

Status: M0. This directory records **architectural decisions already sufficiently justified**
(`PRODUCT_REQUIREMENTS.md` / brief §50, §64). We deliberately keep the set small; we do not create
ADRs for decisions without enough evidence.

## Conventions

Each ADR follows:

```
status        Accepted | Proposed | Superseded
context       why the decision is needed
decision      what was decided
alternatives  considered and why rejected
consequences  what it implies / costs
review        triggers that should re-open this decision
```

- **Accepted** = decision fixed for the indicated scope.
- **Proposed** = direction recorded, but not enough evidence to lock (must be validated in a
  later milestone).
- **Superseded** = replaced by a later ADR (none yet).

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-passive-liveness-first.md) | Passive liveness first | Accepted |
| [ADR-002](ADR-002-burst-capture.md) | Burst image capture instead of single frame | Accepted |
| [ADR-003](ADR-003-server-authoritative.md) | Server-side authoritative decision | Accepted |
| [ADR-004](ADR-004-modular-validators.md) | Modular validator architecture | Accepted |
| [ADR-005](ADR-005-vlm-external-poc-selfhost-prod.md) | External VLM for POC, self-hosted target for production | Accepted (POC) / Proposed (production model) |
| [ADR-006](ADR-006-mssql-metadata-objectstorage-images.md) | MSSQL for metadata, object storage for images | Accepted |
| [ADR-007](ADR-007-react-spa-frontend.md) | React SPA frontend | Accepted |
| [ADR-008](ADR-008-fastapi-backend.md) | FastAPI backend | Accepted |
| [ADR-009](ADR-009-gke-production-target.md) | Kubernetes/GKE production target | Accepted (direction) |

## How decisions are made here

- Security, measurement, auditability, explainability, maintainability, controlled evolution are
  weighted above demo speed (brief §70).
- A decision may be **Proposed** when the architecture requires a direction but the final choice
  must be benchmark- or stakeholder-driven (e.g., production model selection, bank auth standard).
