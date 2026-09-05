# ADR-001 — Passive Liveness First

- **Status:** Accepted
- **Date:** M0

## Context
LivePhoto must decide whether a live human is present. Active liveness (blink/head-turn/smile/
speak/read) adds customer friction and complexity. The product brief mandates a passive-first V1
while preserving the option to add active liveness later.

## Decision
V1 implements **passive liveness** only: burst capture + passive validation layers, with no
customer challenge instructions (no blinking on command, head-turn, movement, speaking, number
reading, or video). Active liveness is architecturally reserved as a later addition on the same
session/capture pipeline.

## Alternatives considered
- **Active liveness first** — rejected: higher friction, worse UX on varied devices, slower
  roll-out; passive-first is the product requirement and allows progressive strengthening.
- **No liveness (single static photo)** — rejected: unacceptable spoof risk for banking.

## Consequences
- Simpler V1 UX and faster time-to-value.
- Residual risk against high-fidelity spoofs must be measured per attack class, not assumed away.
- The pipeline must keep burst frames and validator structure so active/temporal signals can be
  added (M22/M23) without a rewrite.

## Future review triggers
- If benchmark evidence shows passive liveness is insufficient for the bank's risk appetite
  (M5/M9), M23 (optional active liveness) is activated.
