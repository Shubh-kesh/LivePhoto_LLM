# ADR-006 — MSSQL for Metadata, Object Storage for Images

- **Status:** Accepted
- **Date:** M0

## Context
Biometric images are large and highly sensitive; storing production Base64 images directly in MSSQL
business tables is discouraged. The database must hold transaction/capture metadata, decisions,
scores, versions, audit, and review state; image bytes must live elsewhere with controlled access
and lifecycle.

## Decision
- **Microsoft SQL Server** stores metadata: session/capture metadata, validation outputs,
  decisions, scores, model/threshold/policy versions, audit data, review status, callback records,
  and object-storage references + hashes + timestamps.
- **Object storage** (bank-approved, private, encrypted) stores the image bytes (frames and final
  photograph). MSSQL references images by `object_id`/`object_key`/hash/mime/size/timestamp/
  retention state.
- **No production Base64/biometric images inside primary MSSQL business tables** unless a
  separately approved requirement appears.
- Database abstraction keeps SQL Server-specific logic from leaking into business services;
  migrations use **Alembic**.

## Alternatives considered
- **Images in MSSQL (VARBINARY/Base64)** — rejected: bloat, slower queries, harder lifecycle and
  egress control for a highly sensitive class.
- **Filesystem only** — rejected: no metadata/audit/lifecycle integration.

## Consequences
- Clear storage responsibility split (`DATA_MODEL.md` §3).
- Object storage must enforce private buckets, encryption, signed access, access logging, and
  lifecycle deletion (`SECURITY_REQUIREMENTS.md`, `DATA_GOVERNANCE.md`).

## Future review triggers
- If object-storage provider choice changes (bank-approved storage, question #7) or a documented
  need to store small images in the DB arises.
