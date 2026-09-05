# ADR-002 — Burst Image Capture Instead of Single Frame

- **Status:** Accepted
- **Date:** M0

## Context
Designing around a single isolated image makes quality and liveness evaluation fragile and
provides no temporal evidence. The product brief prefers a short burst (6–12 frames over ~1–2 s).

## Decision
Capture a short **burst of 6–12 frames over ~1–2 s** (configurable via `capture_config_version`),
then run lightweight quality screening, select the best candidate frame(s), run liveness/spoof
validations, and finally select one customer photograph. This remains a **photo-based** experience;
**no full video is stored** by the product design. Most raw frames are transient; a configurable
small set is retained as audit evidence.

## Alternatives considered
- **Single frame** — rejected: no redundancy for quality, no temporal signals, higher
  false-reject and weaker PAD.
- **Record a video and extract frames server-side** — rejected: higher data/retention/privacy
  surface, larger uploads, longer processing; the burst achieves the needed redundancy with a
  photo-sized footprint.

## Consequences
- Better best-frame selection and RETRY experience.
- Enables future temporal liveness signals (micro-motion, landmark/illumination/reflection/moiré/
  depth consistency) reusing the burst (M22).
- Frame count/duration and retention are configurable and versioned.

## Future review triggers
- If temporal signals require more frames or different cadence, revisit burst parameters at M22.
