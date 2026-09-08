---
name: livephoto-milestone
description: Use when implementing any LivePhoto milestone (M5.8 or later, or M3-M5.x style feature milestones) to produce an evidence-based implementation plan and completion report. Triggers on "milestone", "M5.8", "implement", or "plan" in LivePhoto tasks.
---

# LivePhoto Milestone Guidance

Guide implementation of any LivePhoto milestone. Read instructions first, then inspect, plan,
implement incrementally with tests, run regressions, and report evidence honestly.

## Workflow

1. **Read instructions.** Read the root `AGENTS.md`, then the scoped `backend/AGENTS.md` and/or
   `frontend/AGENTS.md` as relevant.
2. **Read context.** Read `docs/ROADMAP.md` and the architecture/docs relevant to the milestone
   (e.g. `docs/ARCHITECTURE_PRINCIPLES.md`, `docs/CAPTURE_UX_DESIGN.md`,
   `docs/TRANSACTION_FILE_STORAGE.md`, `docs/PORTRAIT_PROCESSING.md`).
3. **Inspect the existing implementation** before planning — do not assume paths or commands.
4. **Identify current invariants** (security boundaries, server-authoritative decisions,
   filesystem storage, no M6 work, etc.).
5. **Identify the requested change** and the **explicitly out-of-scope work** (do not begin a later
   milestone opportunistically).
6. **Create a concrete implementation plan** (files, behaviors, tests, env/config changes).
7. **Implement incrementally**, adding a test with each behavior change.
8. **Run regressions** with the repository's real commands (see root `AGENTS.md` → Testing).
9. **Review `.env.example`** changes and produce the `LOCAL .ENV ACTION REQUIRED` section if any.
10. **Inspect the git diff** (`git status`, `git diff --check`, `git diff`); never commit secrets,
    model weights, captures, or runtime artifacts.
11. **Generate an evidence-based completion report** distinguishing each claim as:
    `implemented`, `tested`, `manually verified`, `not tested`, `known limitation`.
    Never call engineering-complete work accuracy-validated without evidence; never make
    spoof/liveness accuracy claims from mock/synthetic tests.

## Completion report template

Use the milestone's required report shape when provided. Otherwise include:

- what was implemented (with files),
- what was tested (with exact test commands and counts),
- what was manually verified vs not tested,
- known limitations,
- `LOCAL .ENV ACTION REQUIRED` (or `None.`),
- git status/commit,
- a status line: `COMPLETE` / `PARTIAL` / `NOT COMPLETE` with reasons.