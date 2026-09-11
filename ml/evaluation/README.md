# ML evaluation

Placeholder for the evaluation harness defined in `docs/MODEL_EVALUATION_STRATEGY.md`
(Experiments A/B/C on one leakage-safe dataset, APCER/BPCER per attack class). Created in M5/M9 —
empty in M1.

## Offline portrait-segmentation fallback benchmark

- Report: `docs/PORTRAIT_SEGMENTATION_EVALUATION.md`
- Harness: `backend/scripts/evaluate_portrait_segmentation.py` (developer-only; not production).
- Machine-readable results: `segmentation-eval/segmentation-evaluation.json`

This is an isolated research artifact for a *potential* future fallback matting model
(BiRefNet recommended for a POC). It is **not** integrated into the customer flow and does not
change production portrait behaviour.
