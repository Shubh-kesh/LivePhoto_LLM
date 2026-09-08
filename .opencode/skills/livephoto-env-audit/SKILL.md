---
name: livephoto-env-audit
description: Use after any LivePhoto change that touches configuration or environment to audit `.env.example`/settings/runtime-config changes and produce the exact LOCAL .ENV ACTION REQUIRED section. Triggers on ".env", "environment variable", "env audit", "LOCAL .ENV ACTION REQUIRED".
---

# LivePhoto Env Audit

Audit configuration changes and report exactly what the developer must add/change in their local
`.env`. Never read or print secret values from the actual `.env` file.

## Workflow

1. Compare `.env.example` against the milestone diff.
2. Identify **added** variables, **changed** defaults, **deleted** variables.
3. Inspect settings code changes (backend `Settings` in `app/core/config.py`).
4. Inspect frontend runtime-config changes (`frontend/public/runtime-config.js`,
   `frontend/src/lib/runtimeConfig.ts`, `LIVEPHOTO_*` container vars).
5. Report the exact local `.env` action.

## Output

```text
LOCAL .ENV ACTION REQUIRED

Added:
- VAR_NAME=value_or_placeholder

Changed:
- VAR_NAME=old -> new

Removed:
- VAR_NAME

Exact local values:
VAR_NAME=...
```

If there are no changes:

```text
LOCAL .ENV ACTION REQUIRED
None.
```

Rules:

- Do not automatically edit the real `.env`.
- Never print secret values (mask keys/tokens/passwords).
- Placeholder values (e.g. `<set-locally>`) are acceptable when the value is a secret; exact
  non-secret defaults should be shown.
- Only report variables that actually changed in this milestone.