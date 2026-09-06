# LivePhoto — M5 Dataset Bootstrap (Public Dataset Discovery & Licensing)

Status: M5 baseline (continuation). Documented per M5 §105-108 and the M5 continuation brief.

## Dataset use purpose

```
M5 DATASET USE PURPOSE = NON_COMMERCIAL_POC_RESEARCH
```

Public datasets are used ONLY for a non-commercial POC/research evaluation. They are NOT used for
production, sold, redistributed, incorporated into a commercial training dataset, used to train a
production banking model, or used as production customer data. Any future commercial use requires a
completely separate dataset/license review (continuation §1, §48). A dataset accepted for M5 POC is
therefore NOT automatically approved for any commercial purpose.

## License model

Dataset license state is assessed **under the NON_COMMERCIAL_POC_RESEARCH purpose** (not under a
hypothetical commercial context):

| State | Meaning |
|---|---|
| `ALLOWED_FOR_POC` | Terms reasonably allow non-commercial research evaluation **and** our intended external VLM processing |
| `ALLOWED_FOR_LOCAL_ONLY` | Non-commercial research locally is permitted, but external VLM processing is questionable/prohibited |
| `REQUIRES_APPROVAL` | EULA / institutional / owner permission required |
| `NOT_ALLOWED` | Terms clearly prohibit the intended use |
| `UNCLEAR` | Published terms insufficient to determine external-processing acceptability |

The relevant question is now: *does the dataset permit this specific non-commercial POC/research
evaluation, including external VLM processing?* — not *could it ever be used commercially?*

## Selected dataset

**Axon public face-anti-spoofing sample** (`AxonData/face-anti-spoofing-dataset` on Hugging Face).

- **Official source:** Axon Labs / AxonData (the Hugging Face publication is the original source;
  a Kaggle mirror exists but does not override the license).
- **License:** CC BY-NC 4.0.
- **Purpose assessment:** For NON_COMMERCIAL_POC_RESEARCH with attribution, non-commercial
  evaluation including sending a selected subset to an external VLM is **reasonably permitted**
  (API processing is not redistribution). NOT for production/commercial use.
- **License state:** `ALLOWED_FOR_POC`; external VLM processing: `ALLOWED` (with attribution and
  no commercial use).
- **Classes available in the sample:** `LIVE` (Selfies, 24 stills), `SCREEN_MOBILE`
  (Replay_mobile_attacks, 10 videos), `SCREEN_DISPLAY` (Replay_display_attacks/Screen, 5 videos).
  Mask classes exist (3D paper, cut-out, latex, silicone, textile, wrapped) but are outside the
  M5 four-class scope. **No PRINT_PHOTO class is present** — reported as a class gap.
- **External-processing assessment:** sending the selected subset to Gemini for the POC is treated
  as non-commercial processing; attribution required; no redistribution.
- **Download:** `app/experiments/vlm/datasets/axon.py` → git-ignored `local-data/vlm-baseline/`.

## Other datasets investigated (reassessed under POC purpose)

| Dataset | Source | License state | External VLM |
|---|---|---|---|
| CelebA-Spoof | GitHub open-the-loop/celebA-spoof | `ALLOWED_FOR_LOCAL_ONLY` | `NOT_ALLOWED` (keep local; do not submit externally) |
| Replay-Attack | Idiap | `REQUIRES_APPROVAL` (signed agreement) | `NOT_ALLOWED` |
| Replay-Mobile | Idiap | `REQUIRES_APPROVAL` (signed agreement) | `NOT_ALLOWED` |
| OULU-NPU | University of Oulu | `REQUIRES_APPROVAL` (EULA/terms) | `NOT_ALLOWED` |
| SiW (MSU) | Michigan State University | `REQUIRES_APPROVAL` (institutional) | `NOT_ALLOWED` |

A mirror (Kaggle/Hugging Face/GitHub/Drive) does **not** override the original license.

## Bootstrap procedure (reproducible)

1. `python -m app.experiments.vlm.datasets.axon`-style downloader writes a raw manifest
   (`local-data/vlm-baseline/raw_manifest.jsonl`) with source dataset/sample/label, subject alias,
   device classes.
2. `bootstrap.build_manifest` maps labels (`live`→LIVE, `mobile`→SCREEN_MOBILE,
   `screen_display`→SCREEN_DISPLAY), extracts deterministic frames from videos
   (single = 50% midpoint; triad = 25/50/75%, `frame-extraction-v1`), samples deterministically
   (`sampling-v1`), creates subject-disjoint dev/holdout splits (`split-v1`), and writes
   `manifest.jsonl` with full traceability (source dataset/sample/label, canonical label, split,
   subject alias, device classes, border visibility, lighting, `license_status`, `usage_purpose`).
3. `uv run python -m app.experiments.vlm.validate_dataset --manifest ... --output ...` produces
   `dataset_validation.json` (unique IDs, valid labels, file existence, JPEG decode, SHA-256
   duplicates, path-traversal rejection, split validity).

## Commercial-future warning

Any dataset accepted for the M5 POC is NOT automatically approved for production use, commercial
training, bank deployment, model fine-tuning, or redistribution. A new license/governance review is
required before any commercial purpose (continuation §48).

## POC composition (as built)

- LIVE: 24, SCREEN_MOBILE: 10, SCREEN_DISPLAY: 5 (total 39). PRINT_PHOTO: **0** (class gap; no
  print class in the Axon sample — not fabricated).
- Split: development 8 / holdout 31 (subject-disjoint).
- Frames: LIVE = native stills (1 frame each); video classes = 3 extracted frames each.