# ADR-004 — Modular Validator Architecture

- **Status:** Accepted
- **Date:** M0

## Context
LivePhoto must not be `Image -> LLM -> LIVE/SPOOF`. A single model failure or weakness must not
silently become a banking decision, and layers (face, quality, screen/device, PAD, VLM, temporal)
must be independently improvable and measurable.

## Decision
Validation is a layered pipeline of **independent, replaceable, versioned validators** that expose
a single normalized contract (`name`, `version`, `validate`, `health`, normalized
`ValidationResult` with raw/calibrated score, threshold, reason codes, versions, latency). The
**scoring engine** combines evidence and the **policy engine** maps it to
`PASS/RETRY/REVIEW/FAIL`. No validator makes the business decision directly. Validators are
registered by name/config so any layer can be swapped.

## Alternatives considered
- **Monolithic single-model scorer** — rejected: no replaceability, no per-layer observability,
  hard to reason about failures.
- **Free-form model outputs** — rejected: LLM confidence is not calibrated; deterministic reason
  codes are required.

## Consequences
- More orchestration code up front, but each validator is independently benchmarked and swapped.
- Parallelization of validators is possible later (M8) without changing validator internals.
- The `VisionProvider` abstraction (Gemini/OpenRouter/Groq/Local/Mock) is a concrete instance.

## Future review triggers
- If fusion methodology (M8) or performance demands a different split, revisit, but preserve the
  evidence-vs-decision separation (P4).
