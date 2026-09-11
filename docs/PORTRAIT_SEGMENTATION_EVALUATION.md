# LivePhoto — Offline Portrait Segmentation Fallback Benchmark

Status: **EVALUATION / RESEARCH — NOT PRODUCTION.** This document reports an offline benchmark of
candidate segmentation models for a *potential future* fallback. **No fallback is integrated into
the customer flow.** The current portrait pipeline (`docs/PORTRAIT_PROCESSING.md`) is unchanged.

Machine-readable results: `ml/evaluation/segmentation-eval/segmentation-evaluation.json`.
Harness: `backend/scripts/evaluate_portrait_segmentation.py` (developer-only; never imported by the
application, never started with the backend).

---

## 1. Question

MODNet can produce a structurally corrupted raw matte on difficult captures (confirmed real failure
`LP-20260910T150524236Z-7B4136`), which now fails closed as `PORTRAIT_QUALITY_FAILED`. Before
proposing any production fallback, determine whether another **dedicated segmentation/matting**
model can recover such cases while preserving the original person's pixels and **not regressing**
healthy MODNet cases.

### Identity rule (non-negotiable)

Allowed transformation: **original subject pixels + alpha mask + crop + solid background**. Not
allowed: any generative/AI reconstruction of face, hair, spectacles, beard, or clothing. The
fallback must be segmentation/matting only. The harness composites the model's **raw alpha** with
the production crop/composite code; no generative model is used.

### Privacy / locality

All inference ran **locally** on an Apple M2 (MPS). Test/customer images were **never uploaded** to
any external model/API. Only model weights were downloaded to the Hugging Face cache. Per-image
outputs live under the git-ignored `local-data/segmentation-eval/` directory.

---

## 2. Harness

- Location: `backend/scripts/evaluate_portrait_segmentation.py`.
- Isolation: only `numpy`/`PIL` and the numpy-only production modules
  (`app.portrait.integrity`, `.matte`, `.crop`, `.background`) plus the MODNet ONNX provider; torch/
  transformers are imported lazily inside model adapters. It is not wired into FastAPI or startup.
- Every model is scored with the **same** production validator
  (`app.portrait.integrity.validate_portrait_matte`, `portrait-matte-integrity-v1`). No
  easier/favourable second validator exists.
- CLI: `--input`/`--face-box`/`--manifest`, `--models`, `--output-dir`, `--json-out`,
  `--background-color`, `--device`, `--markdown-out`, per-model repo overrides.
- Outputs per image/model: `original.jpg`, `alpha.png`, `foreground-mask.png`,
  `white-composite.jpg`.
- Metrics recorded per result: model name/version/revision/checkpoint SHA-256, weights size, input
  and output dimensions, inference time, alpha stats, raw and refined integrity (`ok`, reason, face
  retention, head retention, left/right retention, balance, component-face-overlap,
  foreground ratio), and refinement action.

### Isolated environment (exact)

Torch and transformers are **not** backend dependencies and were installed into a throwaway venv
outside the repository (inheriting nothing from `backend/`):

```bash
uv venv --python <python3.13> /tmp/lp-seg
uv pip install --python /tmp/lp-seg/bin/python \
  "torch>=2.6" torchvision transformers kornia timm safetensors huggingface_hub einops \
  "pydantic>=2.9" "pydantic-settings>=2.5" "structlog>=24.4" "onnxruntime>=1.18"
```

Recorded versions: Python 3.13.5, torch 2.14.0 (MPS), torchvision 0.29.0, transformers 4.57.6,
kornia 0.8.3, timm 1.0.29, onnxruntime 1.30.0, numpy 2.x, Pillow 11.x.

> transformers 5.x removed `trust_remote_code`, so **4.57.6** was used for BiRefNet. SAM 2.1 is
> natively supported.

### Backend regression

The harness is additive; it does not modify `app/`, `pyproject.toml`, `.env`, or `.env.example`.

---

## 3. Models, versions, licensing

| Model | Repo | Code license | Weight license | Commercial use | Self-host | Bank suitability |
|---|---|---|---|---|---|---|
| MODNet (baseline) | `ZHKKKe/MODNet` (mirror `DavG25/…`) | Apache-2.0 | Apache-2.0 | Permitted | Yes (ONNX, CPU) | Already in use |
| **BiRefNet** | `ZhengPeng7/BiRefNet` | MIT | MIT (HF model card) | Permitted | Yes (torch/ONNX) | **Suitable** |
| **SAM 2.1** | `facebook/sam2.1-hiera-large` | Apache-2.0 | Apache-2.0 | Permitted | Yes (torch) | Suitable license-wise |
| **BRIA RMBG-2.0** | `briaai/RMBG-2.0` | `bria-rmbg-2.0` | **CC BY-NC 4.0** | **NOT permitted without a commercial agreement with BRIA** | Yes (but gated) | **Disqualified as-is** |

Provenance actually resolved during evaluation:

| Model | Revision | Weights file size | SHA-256 |
|---|---|---|---|
| MODNet | (mirror) | 25,888,640 B | `07c308cf0fc7e6e8b2065a12ed7fc07e1de8febb7dc7839d7b7f15dd66584df9` |
| BiRefNet | `e2bf8e4460fc…` | 444,473,596 B | `9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154` |
| SAM 2.1 | `665f8e2ad61c…` | 897,897,416 B | `dc407dce21301fd94abb395c5099b4f2c455fdc8a8f261ac3d0ea6d4cd197230` |

**RMBG-2.0 was not evaluated:** its weights are license-gated and licensed **non-commercial**
(CC BY-NC 4.0). Downloading/evaluating it adds no decision value because it cannot be used in a bank
production deployment without a paid agreement, and the release notes state commercial use requires
a commercial agreement with BRIA. This is a licensing-based exclusion, not a quality judgement.

---

## 4. Evaluation data

Four local real captures (no synthetic data). Visual attributes were manually inspected.

| Case | Transaction | Size | Attributes |
|---|---|---|---|
| A — known failure | `LP-20260910T150524236Z-7B4136` | 720×1280 | Night scene, harsh point-light flare, spectacles, beard, dark background, white t-shirt, distant background person (seated) + motorbikes |
| B1 — healthy | `LP-20260910T150406247Z-A74038` | 720×1280 | Bright indoor, curly dark hair, dark green tank top, gold chain; legacy capture, **approximate** face box |
| B2 — healthy | `LP-20260911T032327577Z-C6BF3D` | 1280×720 | Office, dark black jacket over beige shirt, curly hair, bright/white background |
| B3 — healthy | `LP-20260911T032414363Z-BA851E` | 1280×720 | Same session/person as B2 |

Face boxes: A from the task brief; B2/B3 from the **persisted production** capture metadata; B1 has
no persisted box (legacy), so an approximate OpenCV Haar box was used and is labelled guidance-only.

Missing categories (not present locally): low-light **without** flash, explicit harsh-flash studio,
dedicated dark-clothing-on-dark-background, dedicated white-clothing-on-white-background, prominent
(main-subject) background person, and a large labelled difficulty set. See §8.

---

## 5. Results (raw alpha, production integrity validator)

| Case | Model | Integrity | Face retention | Head retention | Balance | Component overlap | Time (ms) | Notes |
|---|---|---|---|---|---|---|---|---|
| A known failure | MODNet | **FAIL** (`face_retention_low`) | 0.233 | 0.168 | 0.331 | 0.057 | 162 | Confirmed corruption reproduced |
| A known failure | **BiRefNet** | **PASS** | 0.986 | 0.513 | 0.972 | 0.986 | 3532 | Recovers the failure |
| A known failure | SAM2.1 | PASS | 0.977 | 0.503 | 0.959 | 0.977 | 1692 | Hard-edged, torso truncated |
| B1 healthy | MODNet | PASS | 0.830 | 0.508 | 0.938 | 0.830 | 187 | Baseline |
| B1 healthy | BiRefNet | PASS | 0.831 | 0.531 | 0.924 | 0.831 | 4083 | No regression |
| B1 healthy | SAM2.1 | **FAIL** (`face_retention_low`) | 0.260 | 0.195 | 0.968 | 0.128 | 1322 | Severe under-segmentation |
| B2 healthy | MODNet | PASS | 0.972 | 0.712 | 0.991 | 0.972 | 175 | Baseline |
| B2 healthy | BiRefNet | PASS | 0.969 | 0.708 | 0.994 | 0.969 | 2737 | No meaningful regression |
| B2 healthy | SAM2.1 | **FAIL** (`head_retention_low`) | 0.859 | 0.444 | 0.988 | 0.859 | 1304 | Head/hair truncated |
| B3 healthy | MODNet | PASS | 0.972 | 0.730 | 0.973 | 0.972 | 155 | Baseline |
| B3 healthy | BiRefNet | PASS | 0.969 | 0.726 | 0.970 | 0.969 | 2542 | No meaningful regression |
| B3 healthy | SAM2.1 | **FAIL** (`head_retention_low`) | 0.857 | 0.439 | 0.909 | 0.857 | 1308 | Head/hair truncated |

Foreground ratios (fraction of pixels ≥ 0.5): BiRefNet 0.30–0.55; MODNet 0.23–0.49; SAM2.1 0.11–0.15
on healthy cases (under-segmentation) and 0.145 on the failure.

Refinement (`matte-refinement-v3`) applied to every candidate matte: BiRefNet refined successfully
on all four cases; SAM2.1 was rejected/reverted to raw on the healthy cases (refinement could not
rescue the truncated mask); MODNet was reverted to raw on the failure (as designed).

---

## 6. Model comparison — known failure (`LP-20260910T150524236Z-7B4136`)

| Question | MODNet | BiRefNet | SAM2.1 |
|---|---|---|---|
| Preserve complete primary face? | No — left half erased | **Yes** | Mostly (hard edge) |
| Preserve head/hair? | No | **Yes** | Partially (hair clipped) |
| Avoid asymmetric subject deletion? | No (L 0.116 vs R 0.349) | **Yes** (L 1.000 / R 0.972) | Yes-ish |
| Remove background adequately? | N/A (broken) | **Yes** (soft hair edge) | Yes, but hard mask |
| Pass the existing integrity validator? | No | **Yes** | Yes |
| Preserve original subject pixels (no generation)? | N/A | **Yes** (visual inspection) | Yes |
| Inference latency (M2 MPS, per image) | 0.16 s | ~3.5 s | ~1.7 s |
| Model size / resource impact | 26 MB | 444 MB | 898 MB |

Visual inspection of `white-composite.jpg`:
- **MODNet:** large white holes through the face/head; glasses temple detached; unusable.
- **BiRefNet:** complete face, hair, beard, and spectacles preserved; clean white background; white
  t-shirt naturally blends into the white background (expected for a white-on-white clothing case).
- **SAM2.1:** face/glasses preserved but with a hard binary edge (no soft hair) and the torso is cut
  off just below the beard.

### Healthy cases

| Question | MODNet | BiRefNet | SAM2.1 |
|---|---|---|---|
| Regress edge quality? | baseline | No (comparable) | Yes — hard edges |
| Retain unwanted objects? | No | No | N/A |
| Retain background people? | No | No (not present in B cases) | No |
| Damage clothing/hair? | No | No meaningful difference (0.972 → 0.969) | Yes — head/hair loss |
| Pass existing integrity checks? | Yes (3/3) | Yes (3/3) | **No (0/3)** |

---

## 7. Latency / resource comparison

| Model | Weights | Load (cached, M2 MPS) | Inference / image | Backend |
|---|---|---|---|---|
| MODNet | 26 MB | 0.25 s | 0.16–0.19 s | ONNX Runtime CPU |
| BiRefNet | 444 MB | ~5 s | 2.5–4.1 s | torch + transformers (MPS) |
| SAM2.1 | 898 MB | ~9 s | 1.3–1.7 s | torch + transformers (MPS) |

Operationally: BiRefNet is ~20× slower than MODNet per image on this hardware but still seconds, and
would be invoked only on the **rare** integrity-failure path if ever adopted. CPU-only inference
would be slower; a future UAT/GKE GPU node could serve it. No hard SLA exists yet.

---

## 8. Background people

The known-failure image contains a distant seated person and motorbikes. BiRefNet removed the entire
background including the distant person while preserving the primary subject. We do **not** have a
case that exercises the `LIVE + MULTIPLE + BACKGROUND` portrait path directly (where a background
person is retained by the VLM as portrait-eligible). That behaviour is therefore **not tested**;
VLM `MULTIPLE/BACKGROUND` logic was not touched.

**Missing categories to collect before a production decision:** dedicated distant-background-person,
low-light-no-flash, harsh-flash, white-on-white, dark-on-dark, headwear/spectacles-heavy, and a
larger labelled set per difficulty class.

---

## 9. Recommendation

### Acceptance-criteria assessment (BiRefNet)

| Criterion | Assessment |
|---|---|
| Materially recovers MODNet failures | Yes (1/1 known failure; needs more failures) |
| Healthy cases not meaningfully degraded | Yes (3/3 PASS; metrics within ~0.3 pp of MODNet) |
| Face/head/hair integrity acceptable | Yes (face 0.986, head 0.513, overlap 0.986 on failure) |
| Background removal acceptable | Yes (visual inspection) |
| Distant background people handled | Neutral/untested for MULTIPLE+BACKGROUND |
| Same existing integrity validator passes | Yes |
| Latency operationally acceptable | Plausible for a rare path; needs UAT measurement |
| Self-hostable | Yes |
| License fits commercial/bank deployment | Yes (MIT for code and weights) |
| Resource requirements feasible for UAT/GKE | 444 MB weights; GPU recommended but not mandatory |

### Classification

| Model | Classification | Rationale |
|---|---|---|
| **BiRefNet** | **RECOMMENDED FOR FALLBACK POC** | Recovers the confirmed failure and passes all healthy cases with MIT licensing; needs broader difficult-case data and a UAT latency/resource POC before any production decision. |
| SAM 2.1 | **NOT RECOMMENDED** (as a drop-in fallback) | Failed all three healthy cases under the single-box prompt strategy (head/hair truncation, hard masks). Apache-2.0 license is fine; behaviour is not. Would require a different prompting/automatic-mask approach and re-evaluation. |
| BRIA RMBG-2.0 | **NOT RECOMMENDED** | Non-commercial (CC BY-NC 4.0) and license-gated; unsuitable for a bank production deployment without a paid commercial agreement. Not evaluated. |

**Do not implement production fallback yet.** The correct next step is `MORE DATA REQUIRED` on
difficult categories plus a non-production BiRefNet POC to confirm latency/resource and
`MULTIPLE + BACKGROUND` behaviour. If integrated later, the fallback must:

1. run only after the existing integrity gate fails on the **same original capture**,
2. pass the **same** integrity validator,
3. preserve original pixels only (no generation),
4. keep the same capture/PASS authorization and single-flight/stale handling,
5. and never weaken `PORTRAIT_QUALITY_FAILED`.

---

## 10. Future audit metadata (proposed, NOT IMPLEMENTED)

If a fallback is ever integrated, portrait processing metadata could record:

```text
primary_model
primary_model_version
primary_integrity_result
fallback_attempted
fallback_model
fallback_model_version
fallback_integrity_result
selected_model
```

`NOT IMPLEMENTED` in production. The isolated evaluation harness already records per-model
provenance and integrity results in its JSON output.

---

## 11. Reproduction

```bash
# 1. Isolated eval venv (torch/transformers NOT added to backend deps)
uv venv --python <python3.13> /tmp/lp-seg
uv pip install --python /tmp/lp-seg/bin/python \
  "torch>=2.6" torchvision transformers kornia timm safetensors huggingface_hub einops \
  "pydantic>=2.9" "pydantic-settings>=2.5" "structlog>=24.4" "onnxruntime>=1.18"

# 2. Run the benchmark (weights download on first run into ~/.cache/huggingface)
/tmp/lp-seg/bin/python backend/scripts/evaluate_portrait_segmentation.py \
  --manifest local-data/segmentation-eval/cases.json \
  --models modnet,birefnet,sam2 \
  --output-dir local-data/segmentation-eval \
  --portrait-model-path backend/model-assets/modnet_photographic_portrait_matting.onnx \
  --markdown-out local-data/segmentation-eval/results-table.md
```

Weights stay out of git (`backend/model-assets/` and `~/.cache/huggingface` are not tracked);
per-image artifacts contain real people and remain under git-ignored `local-data/`.

---

## 12. Evidence status

- **implemented / tested:** harness, integrity-based scoring, model adapters, weight provenance,
  license review, known-failure and 3 healthy-case runs (`12/12 model-case results`).
- **manually verified:** composites for the known failure; test-case attributes.
- **not tested:** `LIVE + MULTIPLE + BACKGROUND` portrait behaviour; other missing difficulty
  categories; CPU-only and GPU latencies; UAT/GKE resource footprint.
- **known limitation:** conclusions rest on one known failure and three healthy cases; treat the
  recommendation as a POC direction, not an accuracy validation.

Architecture documentation impact: UPDATED
