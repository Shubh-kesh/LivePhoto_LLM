---
description: Audit configuration/env changes and produce the exact LOCAL .ENV ACTION REQUIRED section using the livephoto-env-audit skill.
---

Audit environment/configuration changes in the current diff.

1. Load and follow the `livephoto-env-audit` skill.
2. Compare `.env.example` (and settings/runtime-config changes) against the current diff.
3. Identify added, changed, and removed variables, plus settings code changes and frontend
   runtime-config changes.
4. Output the exact:

   ```text
   LOCAL .ENV ACTION REQUIRED

   Added:
   ...
   Changed:
   ...
   Removed:
   ...
   Exact local values:
   ...
   ```

   or `LOCAL .ENV ACTION REQUIRED\nNone.` when nothing changed.

Never read or print secret values from the actual `.env`.