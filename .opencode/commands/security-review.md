---
description: Run a read-only security review of the current changes using the security-reviewer agent.
---

Run a security review of the current working-tree changes.

1. Run `git status` and `git diff` to establish the current diff.
2. Invoke the `security-reviewer` subagent on the diff (and relevant context).
3. Report findings in severity order (BLOCKER / HIGH / MEDIUM / LOW) with file, behavior, exploit
   scenario, recommended correction, and test needed.
4. Do not modify any files.

Context for the review: LivePhoto banking capture/liveness — server-authoritative decisions,
filesystem transaction storage, VLM/portrait providers, frontend capture gate. Call out auth,
token/session, CSRF/CORS, SSRF/open-redirect, path traversal/symlink escape, filesystem races,
callback/idempotency, and PII/image/log leakage.