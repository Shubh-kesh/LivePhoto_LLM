# ADR-005 — External VLM for POC, Self-Hosted Target for Production

- **Status:** Accepted (POC scope) / **Proposed** (production model choice)
- **Date:** M0

## Context
VLM-based validation is being evaluated (Experiment A). Production biometric images must not
depend on external third-party AI APIs without separate bank security/legal/compliance approval.
The architecture must allow moving from an external provider to a local/self-hosted provider
without rewriting business workflows.

## Decision
- **POC:** external VLM providers (Gemini, Groq-supported vision models, OpenRouter-supported
  vision models) may be used **only with approved, non-sensitive POC/demo images**. A
  `MockVisionProvider` exists for offline testing.
- **Abstraction:** all VLM use goes through a `VisionProvider` interface so `external -> local`
  is a configuration change, not a rewrite.
- **Production direction (Proposed):** self-hosted model inside bank-controlled infrastructure.
  The specific model/GPU is not selected in M0 (open question #8) and must be validated by
  benchmark before production.

## Alternatives considered
- **External VLM in production** — rejected by policy direction (biometric data residency);
  only with separate approval could this be revisited.
- **No VLM at all** — rejected for M0 evaluation purposes; VLM is a candidate evidence layer and
  a provider-agnostic experiment is required (Experiment A vs B vs C).

## Consequences
- POC results must not silently become a production dependency; explicit gate before production.
- Bank testing and production data must not reach external providers by default
  (`DATA_GOVERNANCE.md`).
- Provider latency/cost/calibration variability must be measured (M4/M9).

## Future review triggers
- Production model selection (self-host) is re-opened when benchmark + GPU availability are known.
- Any request to use external VLM on bank data re-opens this ADR and requires approval.
