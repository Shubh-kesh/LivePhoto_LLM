# LivePhoto ML

Model research, evaluation and experiment workspace (M0 `MODEL_EVALUATION_STRATEGY.md`,
`ROADMAP.md` M4–M9, M22).

## Rules

- **This is not production inference code.** Notebooks/experiments here are research artifacts.
- Production inference code must eventually live in controlled application packages after
  evaluation: `backend/app/validators/` and `backend/app/providers/vision/`.
- **Do not commit biometric datasets, production customer images, or internal bank test data.**
  See `datasets/README.md` and `docs/DATA_GOVERNANCE.md`.
- No ML dependencies are installed in M1; model libraries arrive only when a milestone needs them.

## Layout

| Directory | Purpose |
|---|---|
| `evaluation/` | Evaluation harness, benchmark reports, metric tooling (M5/M9) |
| `experiments/` | Experiment A (VLM-only), B (traditional CV/PAD), C (ensemble) research |
| `datasets/` | Dataset manifests and documentation only (no data files) |