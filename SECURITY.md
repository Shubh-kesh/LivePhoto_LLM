# Security Policy for LivePhoto

LivePhoto is a banking-grade passive liveness platform. It will eventually process **biometric
images** (customer photographs). This policy governs how vulnerabilities are reported and what
must never be committed.

## Reporting a vulnerability

Please report suspected security issues privately, **not** in public issue trackers.

- **Security contact:** [to be set by the owning organisation]
- Include: affected component (`backend`, `frontend`, `ml`, `infrastructure`, `docs`),
  reproducible steps, impact, and any suggested fix.
- Please include the environment/version where observed.

## Do not include in reports

- **Real biometric data.** Never attach customer photographs, capture frames, or identity images
  to a security report. Describe the issue with synthetic/dummy data or a redacted sketch instead.
- **Production credentials.** Never attach real tokens, passwords, certificates, or bank
  configuration. Redact all sensitive material.

## Committing code

- Never commit `.env` files, API keys, passwords, certificates, private keys, or secrets of any
  kind. The repository `.gitignore` excludes these; keep it that way.
- Never commit biometric images, customer photographs, internal bank test datasets, or captured
  frames. See `docs/DATA_GOVERNANCE.md`.
- Never add real banking customer data of any kind to this repository.

## Supported branches

- **Stable:** `main` (primary integration branch).
- Security fixes are expected on `main`; patch-versions policy is pending release automation.

## Responsible disclosure

We ask for a reasonable disclosure window before public discussion of a confirmed issue.