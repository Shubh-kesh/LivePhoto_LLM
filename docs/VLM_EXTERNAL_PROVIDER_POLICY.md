# LivePhoto — External VLM Provider Policy (M4)

Status: M4 baseline.

## Scope

This policy governs the use of external vision-language-model providers (Gemini, Groq, OpenRouter)
in the LivePhoto **experiment** path.

## Allowed use

External VLMs are allowed **only** for:

- POC / development.
- Approved, **non-sensitive** test images (synthetic fixtures, clearly-licensed samples,
  developer-provided non-sensitive images with documented provenance).

## Never send to external providers

- Production bank customer images.
- Bank internal biometric datasets.
- Customer PII.
- Aadhaar/PAN images.
- Confidential banking records.

## Rules

- External providers are **POC-only**. Production targets a self-hosted VLM inside bank-controlled
  infrastructure (M0 ADR-005).
- No bank-internal dataset is sent unless explicitly approved.
- No implicit file storage: M4 uses bounded inline requests; provider file-storage APIs are not
  used by default (M4 §14).
- No raw image logging, no Base64/image content in logs, no capture bytes persisted by the
  interactive API (M4 §59, §139).
- API keys are server-side secrets only; the browser never receives provider credentials and never
  calls providers directly (M4 §8, §26).
- The experimental endpoint is disabled by default and refuses to operate in `uat`/`production`
  even if enabled (M4 §11).

## Documentation

- Provider architecture: `docs/VLM_PROVIDER_ARCHITECTURE.md`
- Prompt design: `docs/VLM_PROMPT_DESIGN.md`
- Evaluation: `docs/VLM_BASELINE_EVALUATION.md`