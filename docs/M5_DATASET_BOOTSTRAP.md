# LivePhoto — M5 Dataset Bootstrap (Public Dataset Discovery & Licensing)

Status: M5 baseline. Documented per M5 §105-108.

## Result

**POC DATASET GATE = BLOCKED** (no dataset is legally cleared for this commercial project's
external-VLM benchmark without explicit approval). Engineering tooling is ready; the required user
action is listed at the end.

## Datasets investigated

| Dataset | Official source | Mirror | License / access | Classes | External-VLM processing | Verdict |
|---|---|---|---|---|---|---|
| CelebA-Spoof | GitHub `open-the-loop/celebA-spoof` | n/a | Research/non-commercial terms; attribution expected | LIVE, phone/print | UNCLEAR | NOT ALLOWED without confirmation |
| Replay-Attack | Idiap Research Institute | n/a | Non-commercial research; signed Idiap agreement | LIVE, phone/laptop/print | NOT_ALLOWED | NOT ALLOWED |
| Replay-Mobile | Idiap Research Institute | n/a | Non-commercial research; signed agreement | LIVE, phone/print | NOT_ALLOWED | NOT ALLOWED |
| OULU-NPU | University of Oulu | n/a | Non-commercial research; terms acceptance | LIVE, phone/tablet/print | NOT_ALLOWED | NOT ALLOWED |
| SiW (MSU) | Michigan State University | n/a | Non-commercial research terms | LIVE, phone/print | NOT_ALLOWED | NOT ALLOWED |
| Axon sample sets | Axon (public samples) | n/a | Unclear | LIVE, phone/print | UNCLEAR | LICENSE_REVIEW_REQUIRED |

A Kaggle/Hugging Face mirror does **not** override the original dataset license (M5 §9). None of
the above are used for external-provider benchmarking in M5.

## Selection rule (M5 §8, §12)

A dataset is used only if **all** are reasonably supported: provenance understood; ground-truth
labels exist; usage rights compatible with the current POC (commercial banking intent); third-party
VLM processing allowed or approved; trusted download source. If no dataset qualifies:
**POC DATASET GATE = BLOCKED** (M5 §12, §108).

## External-provider-processing assessment

External API submission of dataset images may constitute third-party processing or distribution.
For all research-only/non-commercial datasets above, external submission is **NOT** treated as
authorized.

## Bootstrap tooling (ready)

- `backend/app/experiments/vlm/datasets/registry.py` — dataset descriptors + honest license state.
- `licensing.py` — `require_usable_dataset` refuses restricted/unknown datasets.
- `sampling.py` — seeded deterministic sampling, subject-diverse sampling, subject/session-disjoint
  dev/holdout splits.
- `labelmap.py` — canonical label mapping; ambiguous labels are never guessed.
- `frame_extraction.py` — deterministic 25/50/75% video-frame extraction (`frame-extraction-v1`).
- `bootstrap.py` — builds the git-ignored output manifest with full traceability
  (source dataset/sample/label, canonical label, split, subject alias, device classes, border
  visibility, lighting, prompt-injection flag).
- `validate_dataset.py` — `uv run python -m app.experiments.vlm.validate_dataset --manifest ...`
  (unique IDs, allowed labels/splits, file existence, JPEG validity, SHA-256 duplicates,
  path-traversal rejection, schema) → `dataset_validation.json`.

## Sampling / split policy (M5 §25-28)

- Deterministic seeded sampling (`sampling-v1`); diversity across subject/device/lighting when
  metadata exists; never "first N files".
- No near-duplicate counting (distinct subjects/sessions/presentation instruments preferred).
- Subject/session-disjoint `development`/`holdout` split (`split-v1`); holdout is not tuned
  against.

## Dataset limitations

- Public PAD images are NOT equivalent to LivePhoto native browser captures (camera pipeline,
  compression, framing, guidance, burst selection, device characteristics differ) — M5 results
  would be labelled `PUBLIC DATASET VLM BASELINE`, never `LIVEPHOTO CAPTURE-PIPELINE BASELINE`
  (M5 §34, §46, §86).

## Required user action to unblock

- Obtain dataset license/EULA approval (e.g., a signed institutional agreement for Replay-Attack,
  Replay-Mobile, OULU-NPU, or confirmation that a chosen dataset's terms permit commercial +
  third-party processing), **or**
- Collect own **consented** POC captures (people physically present → LIVE; photos displayed on
  phone/laptop → screen spoofs; printed photos → print spoofs) with documented provenance, **or**
- Obtain an organization/legal decision that a specific dataset may be used.