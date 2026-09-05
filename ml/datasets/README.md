# Datasets

This directory is **documentation only**. The `.gitignore` excludes all data files placed here.

## Do not commit

- **Biometric datasets** — captured faces, frames, or photographs.
- **Production customer images** — any image of a real banking customer.
- **Internal bank test data** — genuine/spoof captures from the bank testing environment.

## Allowed

- Dataset manifests, READMEs, label schema documentation, and pointers to data stored outside the
  repository under governance (see `docs/DATA_GOVERNANCE.md` for data zones and approvals).

## Data zones reminder

| Zone | Where | External-VLM use |
|---|---|---|
| POC/demo | public/open/synthetic/non-sensitive samples | allowed (approved) |
| Bank testing | bank-internal, controlled | not allowed by default |
| Production | live captures | never external; self-hosted inference |

Do not copy bank-testing or production data into public development environments.