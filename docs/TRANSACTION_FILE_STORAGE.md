# LivePhoto — Transaction File Storage (M5.7)

## Why filesystem storage

**NO GCS. NO S3. NO Azure Blob. NO generic object-storage abstraction.** LivePhoto transaction
storage is a plain **filesystem path** (`FILE_STORAGE_ROOT`). The storage product behind the mount
(enterprise file storage in UAT/production) is invisible to the application.

Deployment model:

```text
LOCAL        → local filesystem directory (backend/local-data/file-storage, git-ignored)
UAT          → mounted enterprise file-storage volume
PRODUCTION   → mounted enterprise file-storage volume
```

The application sees the storage location simply as a path. See
`docs/UAT_RUNTIME_CONFIGURATION.md` for deployment variables.

## Local layout

```text
backend/local-data/file-storage/
└── transactions/
    └── <transaction_id>/
```

`backend/local-data/` is git-ignored; developers can inspect the original capture, VLM result
metadata and processed portrait directly from the backend folder.

## UAT / production mount

Same code, mounted filesystem:

```text
GKE Pod → mounted file-storage volume → /mnt/livephoto
```

```env
FILE_STORAGE_ROOT=/mnt/livephoto
```

No Kubernetes manifests are created in this milestone; infrastructure is manual.

## Transaction creation

Whenever a transaction is initiated, the transaction folder is created **FIRST**:

```text
generate/validate transaction_id
→ create <root>/transactions/<id>/
→ write transaction.json (atomic)
→ continue workflow
```

If folder creation fails, the workflow stops with a typed technical error (`TECHNICAL_ERROR`); it
never continues with undefined storage.

Transaction IDs are opaque, filesystem-safe, globally unique UUID v4 hex (not PII-derived).
Paths are built only from validated IDs and fixed relative artifact paths.

## Folder structure

```text
<FILE_STORAGE_ROOT>/transactions/<transaction_id>/
├── transaction.json          # lifecycle metadata (CREATED → … → PORTRAIT_READY)
├── capture/
│   ├── selected-original.jpg # the unprocessed source (never overwritten)
│   └── capture.json
├── vlm/
│   └── result.json           # normalized VLM result (no image bytes/credentials)
├── portrait/
│   ├── processed.jpg         # processed portrait (deterministic path)
│   └── processing.json
└── tmp/                      # (optional, transient, cleaned after processing)
```

## Artifact references

Application logic refers to artifacts with transaction-relative references, never absolute server
paths:

```python
ArtifactReference(transaction_id=..., artifact_type=..., relative_path=..., content_type=..., size_bytes=..., sha256=...)
```

Supported artifact types: `SELECTED_ORIGINAL_CAPTURE`, `VLM_RESULT`, `PROCESSED_PORTRAIT`,
`PORTRAIT_PROCESSING_RESULT`. This is an internal convention, not a database model (no tables are
added; M5.7 is filesystem-only and does not depend on MSSQL).

## Atomic writes

JSON metadata writes use: temp file → fsync → atomic rename. A process stopping mid-write cannot
corrupt JSON. File permissions are conservative (application-only; never `0777`).

## Security

- Transaction IDs are validated (regex, no dots/slashes) before any path is built.
- Every resolved path is confined below the storage root; `..`, absolute paths and symlink escapes
  are rejected (tested).
- The artifact-read endpoint is a narrow, controlled lookup (`GET /api/v1/transactions/{id}/artifacts/{type}`)
  with allowed artifact types, root confinement, `Cache-Control: no-store`, and no directory
  listing / no arbitrary filename input / no generic static file server.
- Absolute server paths are never exposed to the frontend.

## Retention

Retention/purge is a **later policy concern**; not implemented in M5.7.

## M5.8 integration state

Consumer integration adds shared-filesystem index areas under the same `FILE_STORAGE_ROOT`
(preserving root confinement, atomic writes, symlink protection and conservative permissions):

```text
<FILE_STORAGE_ROOT>/
  transactions/<internal_tx_id>/...   # + launch/active-launches.json, browser/active-session.json,
                                      #   attempts.json, decisions/decision.json,
                                      #   callback/decision-callback.json, .lock
  index/launch-tokens/<sha256>.json       # opaque launch tokens (hash only)
  index/browser-sessions/<sha256>.json    # browser session + CSRF (hashes only)
  index/external/<sha256(consumer:external)>.json   # external -> internal lookup
```

- External transaction IDs are correlation values only; **never** used as filesystem paths (SHA-256
  index filenames instead).
- State transitions (attempt counting, launch revocation, session rotation, status, callback
  dedup) are serialized with a per-transaction `fcntl.flock` on `<tx>/ .lock`.
- Terminal states (`COMPLETED`, `ATTEMPT_LIMIT_EXCEEDED`) cannot restart capture.
- Launch tokens are **reopenable** (until expiry/reissue/terminal state), not one-time capture tokens.