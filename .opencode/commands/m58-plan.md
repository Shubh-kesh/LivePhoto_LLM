---
description: Produce an M5.8 implementation plan only — no code changes. Loads livephoto-milestone, inspects the M5.8 requirements, invokes the livephoto-architect subagent, and outputs a plan.
---

Plan M5.8 without making any code changes.

1. Load and follow the `livephoto-milestone` skill (read `AGENTS.md` + `docs/ROADMAP.md` + relevant
   architecture docs first).
2. Read the current M5.8 requirements from the user prompt (`$ARGUMENTS` if provided).
3. Inspect the existing implementation (do not assume paths/commands).
4. Invoke the `livephoto-architect` subagent against the requested M5.8 change and incorporate its
   plan (affected modules, trust boundaries, concurrency/idempotency, tests, env/config changes).
5. Identify current invariants and explicitly out-of-scope work (no M6, no object storage, no
   browser-authorized decisions unless the requirement explicitly changes them).
6. Produce a concrete, ordered implementation plan with files and behaviors.

Do NOT edit any files. Stop after the plan.