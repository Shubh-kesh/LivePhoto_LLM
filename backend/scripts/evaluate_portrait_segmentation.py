#!/usr/bin/env python3
"""Offline portrait-segmentation fallback benchmark (developer-only; NOT production).

This is an ISOLATED EVALUATION TOOL. It is intentionally:

- **not imported by the application** (nothing under ``app/`` imports this file),
- **not started with the backend** (no FastAPI/startup wiring),
- **not a fallback path** (it never runs during a customer transaction),
- **read-only over the model pipeline** (it reuses the production integrity validator but never
  changes it).

Purpose: before any production fallback segmentation architecture is proposed, benchmark candidate
matting/segmentation models locally against the KNOWN MODNet failure and healthy MODNet cases,
using the SAME integrity validator that gates production portraits
(``app.portrait.integrity.validate_portrait_matte`` / ``portrait-matte-integrity-v1``).

Identity rule (non-negotiable): the only permitted transformation is
``original subject pixels + alpha mask + crop + background composite``. No generative model is used;
candidate alpha mattes only, composited over the configured solid background. We never create or
hallucinate face/hair/clothing pixels.

Privacy: all inference runs LOCALLY. Test/customer images are never uploaded to any external
model/API. Only model weights are downloaded (to the Hugging Face cache); images never leave the
machine. Evaluation image artifacts are written under a local, git-ignored output directory.

Robustness: model runtimes (torch/transformers) are imported lazily. A missing runtime, a gated
model, or a license-unavailable checkpoint is recorded as a SKIPPED result, never as a crash that
hides other results.

Example
-------
    backend/scripts/evaluate_portrait_segmentation.py \
        --input "local-data/file-storage/transactions/LP-.../capture/selected-original.jpg" \
        --face-box "0.36,0.36,0.34,0.26" \
        --models modnet,birefnet,sam2 \
        --output-dir local-data/segmentation-eval
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.portrait.background import composite_solid, parse_background_color  # noqa: E402
from app.portrait.crop import CROP_VERSION, passport_crop  # noqa: E402
from app.portrait.integrity import (  # noqa: E402
    MATTE_INTEGRITY_VERSION,
    MatteIntegrity,
    refinement_is_acceptable,
    validate_portrait_matte,
)
from app.portrait.matte import MATTE_REFINEMENT_VERSION, refine_matte  # noqa: E402
from app.portrait.segmentation import OnnxPortraitSegmentation  # noqa: E402

EVAL_SCHEMA_VERSION = "segmentation-evaluation-v1"
DEFAULT_BACKGROUND_COLOR = "#FFFFFF"
DEFAULT_MODNET_PATH = "model-assets/modnet_photographic_portrait_matting.onnx"
DEFAULT_MODELS = "modnet,birefnet"
FOREGROUND_THRESHOLD = 0.5

#: Static license/operational catalog. Licenses are recorded SEPARATELY for code and weights where
#: they differ. Commercial suitability is the deciding operational constraint for a bank deployment.
MODEL_CATALOG: dict[str, dict[str, str]] = {
    "modnet": {
        "name": "MODNet photographic portrait matting (ONNX)",
        "repo": "ZHKKKe/MODNet (weights mirror: DavG25/modnet-pretrained-models)",
        "code_license": "Apache-2.0",
        "weights_license": "Apache-2.0",
        "commercial_use": "Permitted (permissive, attribution/notice).",
        "source": "https://huggingface.co/DavG25/modnet-pretrained-models",
        "runtime": "onnxruntime (CPU)",
    },
    "birefnet": {
        "name": "BiRefNet dichotomous image segmentation",
        "repo": "ZhengPeng7/BiRefNet",
        "code_license": "MIT",
        "weights_license": "MIT (Hugging Face model card)",
        "commercial_use": "Permitted (permissive, attribution/notice).",
        "source": "https://huggingface.co/ZhengPeng7/BiRefNet",
        "runtime": "torch + transformers (trust_remote_code)",
    },
    "sam2": {
        "name": "SAM 2.1 (Hierarchical Image Segmentation, promptable)",
        "repo": "facebook/sam2.1-hiera-large",
        "code_license": "Apache-2.0",
        "weights_license": "Apache-2.0",
        "commercial_use": "Permitted (permissive, attribution/notice).",
        "source": "https://huggingface.co/facebook/sam2.1-hiera-large",
        "runtime": "torch + transformers (Sam2Model, box prompt)",
    },
    "rmbg2": {
        "name": "BRIA RMBG-2.0 background removal",
        "repo": "briaai/RMBG-2.0",
        "code_license": "bria-rmbg-2.0 (model license)",
        "weights_license": "CC BY-NC 4.0 (non-commercial)",
        "commercial_use": (
            "NOT permitted without a separate commercial agreement with BRIA; HF weights are "
            "gated. Disqualified for a bank production deployment as-is."
        ),
        "source": "https://huggingface.co/briaai/RMBG-2.0",
        "runtime": "torch + transformers (trust_remote_code, gated weights)",
    },
}


@dataclass
class Case:
    name: str
    image_path: Path
    face_box: tuple[float, float, float, float] | None
    notes: str = ""


@dataclass
class ModelSpec:
    key: str
    name: str
    repo: str
    code_license: str
    weights_license: str
    commercial_use: str
    source: str
    runtime: str
    revision: str | None = None
    weights_bytes: int | None = None
    checkpoint_sha256: str | None = None
    load_ms: int | None = None
    license_notes: str = ""


class AlphaProvider(Protocol):
    """Produces a soft alpha matte (0..1) for the primary subject."""

    spec: ModelSpec

    def predict_alpha(
        self,
        image: Image.Image,
        face_box: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray: ...


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _spec_for(key: str) -> ModelSpec:
    entry = MODEL_CATALOG[key]
    return ModelSpec(
        key=key,
        name=entry["name"],
        repo=entry["repo"],
        code_license=entry["code_license"],
        weights_license=entry["weights_license"],
        commercial_use=entry["commercial_use"],
        source=entry["source"],
        runtime=entry["runtime"],
    )


def _pick_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _hf_provenance(
    spec: ModelSpec, *, weights_suffixes: tuple[str, ...] = (".safetensors",)
) -> None:
    """Resolve HF revision + hash the primary weight file (best effort; never fatal)."""
    try:
        from huggingface_hub import HfApi, hf_hub_download

        info = HfApi().model_info(spec.repo, files_metadata=True)
        spec.revision = info.sha
        candidate = None
        for sibling in info.siblings or []:
            name = sibling.rfilename
            if name.endswith(weights_suffixes):
                candidate = sibling
                if name in {"model.safetensors", f"{spec.repo.split('/')[-1]}.safetensors"}:
                    break
        if candidate is not None:
            spec.weights_bytes = candidate.size
            local = Path(hf_hub_download(spec.repo, candidate.rfilename))
            spec.checkpoint_sha256 = _sha256_file(local)
    except Exception as exc:
        spec.license_notes = (spec.license_notes + f" provenance: {type(exc).__name__}").strip()


class OnnxModnetProvider:
    def __init__(self, model_path: Path, expected_sha256: str | None) -> None:
        self.spec = _spec_for("modnet")
        started = time.perf_counter()
        self._provider = OnnxPortraitSegmentation(
            str(model_path), expected_sha256=expected_sha256 or ""
        )
        self.spec.load_ms = int((time.perf_counter() - started) * 1000)
        self.spec.weights_bytes = model_path.stat().st_size if model_path.exists() else None
        if model_path.exists():
            self.spec.checkpoint_sha256 = _sha256_file(model_path)

    def predict_alpha(
        self,
        image: Image.Image,
        face_box: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray:
        return self._provider.predict_alpha(image)


class BiRefNetProvider:
    def __init__(self, repo: str, device: str) -> None:
        self.spec = _spec_for("birefnet")
        self.spec.repo = repo
        self._device = device
        started = time.perf_counter()
        from transformers import AutoModelForImageSegmentation

        self._model = (
            AutoModelForImageSegmentation.from_pretrained(repo, trust_remote_code=True)
            .to(device)
            .eval()
        )
        self.spec.load_ms = int((time.perf_counter() - started) * 1000)
        _hf_provenance(self.spec)

    def predict_alpha(
        self,
        image: Image.Image,
        face_box: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray:
        import torch
        from torchvision import transforms

        rgb = image.convert("RGB")
        transform = transforms.Compose(
            [
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        tensor = transform(rgb).unsqueeze(0).to(self._device)
        with torch.no_grad():
            output = self._model(tensor)
        prediction = output[-1] if isinstance(output, (list, tuple)) else output
        prediction = prediction.sigmoid().cpu()
        alpha = prediction.squeeze().numpy().astype(np.float32)
        resized = np.asarray(
            Image.fromarray((np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)).resize(image.size)
        )
        return resized.astype(np.float32) / 255.0


class Sam2Provider:
    """SAM 2.1 person/foreground segmentation using the primary face box as prompt guidance."""

    def __init__(self, repo: str, device: str) -> None:
        self.spec = _spec_for("sam2")
        self.spec.repo = repo
        self._device = device
        started = time.perf_counter()
        from transformers import Sam2Model, Sam2Processor

        self._processor = Sam2Processor.from_pretrained(repo)
        self._model = Sam2Model.from_pretrained(repo).to(device).eval()
        self.spec.load_ms = int((time.perf_counter() - started) * 1000)
        _hf_provenance(self.spec)

    @staticmethod
    def _prompt_box(
        face_box: tuple[float, float, float, float], size: tuple[int, int]
    ) -> list[float]:
        """Expand the face box to an approximate person region (documented prompt strategy).

        SAM2 is promptable, not a portrait-matting model. Empirical result on the known MODNet
        failure: an OVER-expanded box makes SAM2 select background, while a TIGHT box around
        head/face/upper-torso selects the primary person cleanly. We therefore pad the face box
        only modestly sideways, a little above the hair, and extend downward to the torso.
        """
        width, height = size
        fx, fy, fw, fh = face_box
        x0 = max(0.0, fx - 0.1 * fw)
        x1 = min(1.0, fx + fw + 0.1 * fw)
        y0 = max(0.0, fy - 0.5 * fh)
        y1 = min(1.0, fy + fh + 1.5 * fh)
        return [x0 * width, y0 * height, x1 * width, y1 * height]

    def predict_alpha(
        self,
        image: Image.Image,
        face_box: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray:
        import torch

        if face_box is None:
            raise ValueError("SAM2 requires the normalized primary face box as prompt guidance")
        rgb = image.convert("RGB")
        box = Sam2Provider._prompt_box(face_box, rgb.size)
        inputs = self._processor(images=rgb, input_boxes=[[box]], return_tensors="pt")
        model_inputs = {
            key: (value.to(self._device) if hasattr(value, "to") else value)
            for key, value in inputs.items()
        }
        with torch.no_grad():
            try:
                outputs = self._model(**model_inputs, multimask_output=False)
            except TypeError:
                outputs = self._model(**model_inputs)
        # The SAM2 (video-architecture) checkpoint returns pred_masks with an extra leading
        # singleton dimension, and its processor post_process_masks is version-fragile. We resize
        # and threshold the single predicted mask ourselves (deterministic, version-independent).
        logits = outputs.pred_masks
        while logits.ndim > 3:
            logits = logits[:, 0]
        logits = logits[0].float().cpu().numpy()
        while logits.ndim > 2:
            logits = logits[0]
        probability = 1.0 / (1.0 + np.exp(-logits))
        mask_image = Image.fromarray((np.clip(probability, 0.0, 1.0) * 255).astype(np.uint8))
        resized = np.asarray(mask_image.resize(image.size), dtype=np.float32) / 255.0
        return (resized > 0.5).astype(np.float32)


class Rmbg2Provider:
    def __init__(self, repo: str, device: str) -> None:
        self.spec = _spec_for("rmbg2")
        self.spec.repo = repo
        self._device = device
        started = time.perf_counter()
        from transformers import AutoModelForImageSegmentation

        self._model = (
            AutoModelForImageSegmentation.from_pretrained(repo, trust_remote_code=True)
            .to(device)
            .eval()
        )
        self.spec.load_ms = int((time.perf_counter() - started) * 1000)
        _hf_provenance(self.spec)

    def predict_alpha(
        self,
        image: Image.Image,
        face_box: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray:
        import torch
        from torchvision import transforms

        rgb = image.convert("RGB")
        transform = transforms.Compose(
            [
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        tensor = transform(rgb).unsqueeze(0).to(self._device)
        with torch.no_grad():
            output = self._model(tensor)
        prediction = output[-1] if isinstance(output, (list, tuple)) else output
        prediction = prediction.sigmoid().cpu()
        alpha = prediction.squeeze().numpy().astype(np.float32)
        resized = np.asarray(
            Image.fromarray((np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)).resize(image.size)
        )
        return resized.astype(np.float32) / 255.0


def _build_provider(key: str, args: argparse.Namespace, device: str) -> AlphaProvider:
    if key == "modnet":
        model_path = Path(args.portrait_model_path)
        if not model_path.is_absolute() and not model_path.exists():
            model_path = _BACKEND_ROOT / model_path
        return OnnxModnetProvider(model_path, args.portrait_model_sha256)
    if key == "birefnet":
        return BiRefNetProvider(args.birefnet_repo, device)
    if key == "sam2":
        return Sam2Provider(args.sam2_repo, device)
    if key == "rmbg2":
        return Rmbg2Provider(args.rmbg2_repo, device)
    raise KeyError(key)


def _integrity_dict(integrity: MatteIntegrity) -> dict[str, Any]:
    return asdict(integrity)


def _save_alpha(path: Path, alpha: np.ndarray) -> None:
    Image.fromarray((np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8), mode="L").save(path)


def _composite(
    image: Image.Image,
    alpha: np.ndarray,
    face_box: tuple[float, float, float, float] | None,
    background_rgb: tuple[int, int, int],
) -> tuple[np.ndarray, dict[str, Any]]:
    crop = passport_crop(alpha, (image.width, image.height), face_box_normalized=face_box)
    cropped = image.crop((crop.x0, crop.y0, crop.x1, crop.y1))
    crop_alpha = alpha[crop.y0 : crop.y1, crop.x0 : crop.x1]
    foreground = np.asarray(cropped.convert("RGB"))
    composed = composite_solid(foreground, crop_alpha, background_rgb)
    metadata = {
        "x0": crop.x0,
        "y0": crop.y0,
        "x1": crop.x1,
        "y1": crop.y1,
        "width": crop.width,
        "height": crop.height,
        "normalized": list(crop.normalized),
    }
    return composed, metadata


def _evaluate_case_model(
    case: Case,
    provider: AlphaProvider,
    output_root: Path,
    background_rgb: tuple[int, int, int],
) -> dict[str, Any]:
    model_dir = output_root / case.name / provider.spec.key
    model_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(case.image_path)
    image.load()
    image = image.convert("RGB")

    result: dict[str, Any] = {
        "case": case.name,
        "model": provider.spec.key,
        "status": "OK",
        "input_dimensions": {"width": image.width, "height": image.height},
        "output_dimensions": None,
        "inference_ms": None,
        "alpha_stats": None,
        "raw_integrity": None,
        "refined_integrity": None,
        "refinement_action": None,
        "crop_box": None,
        "outputs": {},
        "error": None,
    }

    original_path = model_dir / "original.jpg"
    image.save(original_path, format="JPEG", quality=95)
    result["outputs"]["original"] = str(original_path.relative_to(output_root))

    try:
        started = time.perf_counter()
        alpha = np.asarray(provider.predict_alpha(image, case.face_box), dtype=np.float32)
        result["inference_ms"] = int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    if alpha.shape != (image.height, image.width):
        result["status"] = "ERROR"
        result["error"] = f"alpha shape {alpha.shape} != image {(image.height, image.width)}"
        return result

    result["alpha_stats"] = {
        "min": round(float(alpha.min()), 4),
        "max": round(float(alpha.max()), 4),
        "mean": round(float(alpha.mean()), 4),
        "shape": list(alpha.shape),
    }
    alpha_path = model_dir / "alpha.png"
    _save_alpha(alpha_path, alpha)
    result["outputs"]["alpha"] = str(alpha_path.relative_to(output_root))

    mask_path = model_dir / "foreground-mask.png"
    mask = (alpha >= FOREGROUND_THRESHOLD).astype(np.uint8) * 255
    Image.fromarray(mask, mode="L").save(mask_path)
    result["outputs"]["foreground_mask"] = str(mask_path.relative_to(output_root))

    raw_integrity = validate_portrait_matte(alpha, case.face_box)
    refined_alpha = refine_matte(alpha, face_box_normalized=case.face_box)
    refined_integrity = validate_portrait_matte(refined_alpha, case.face_box)
    acceptable = refinement_is_acceptable(raw_integrity, refined_integrity)

    result["raw_integrity"] = _integrity_dict(raw_integrity)
    result["refined_integrity"] = _integrity_dict(refined_integrity)
    result["refinement_action"] = "refined" if acceptable else "reverted_to_raw"

    # The composite uses the MODEL'S RAW alpha (no MODNet-specific refinement) so the visual
    # comparison is not biased by production post-processing tuned for MODNet.
    try:
        composed, crop_meta = _composite(image, alpha, case.face_box, background_rgb)
        composite_path = model_dir / "white-composite.jpg"
        Image.fromarray(composed, mode="RGB").save(composite_path, format="JPEG", quality=95)
        result["outputs"]["white_composite"] = str(composite_path.relative_to(output_root))
        result["crop_box"] = crop_meta
        result["output_dimensions"] = {
            "width": int(composed.shape[1]),
            "height": int(composed.shape[0]),
        }
    except Exception as exc:
        result["status"] = "PARTIAL"
        result["error"] = f"composite: {type(exc).__name__}: {exc}"

    return result


def _parse_face_box(value: str) -> tuple[float, float, float, float]:
    parts = [float(p) for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("face box must be 'x,y,w,h' (normalized)")
    return (parts[0], parts[1], parts[2], parts[3])


def _load_manifest(path: Path) -> list[Case]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases: list[Case] = []
    for entry in data.get("cases", []):
        box = entry.get("face_box")
        cases.append(
            Case(
                name=entry["name"],
                image_path=Path(entry["image"]),
                face_box=tuple(box) if box else None,  # type: ignore[arg-type]
                notes=entry.get("notes", ""),
            )
        )
    return cases


def _collect_cases(args: argparse.Namespace) -> list[Case]:
    cases: list[Case] = []
    if args.manifest:
        cases.extend(_load_manifest(Path(args.manifest)))
    boxes = args.face_box or []
    for index, value in enumerate(args.input):
        box = boxes[index] if index < len(boxes) else (boxes[0] if boxes else None)
        name = Path(value).parent.name or f"case-{index}"
        if Path(value).name == "selected-original.jpg":
            name = Path(value).parent.parent.name or name
        cases.append(Case(name=name, image_path=Path(value), face_box=box))
    return cases


def _write_markdown_table(results: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "| Case | Model | Integrity | Face retention | Head retention | Balance | "
        "Component overlap | Time (ms) | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in results:
        raw = row.get("raw_integrity") or {}
        status = row.get("status")
        if status == "OK":
            integrity = "PASS" if raw.get("ok") else f"FAIL ({raw.get('reason')})"
        else:
            integrity = status
        lines.append(
            "| {case} | {model} | {integrity} | {face} | {head} | {balance} | {overlap} | "
            "{time} | {notes} |".format(
                case=row.get("case"),
                model=row.get("model"),
                integrity=integrity,
                face=raw.get("face_retention", "-"),
                head=raw.get("head_retention", "-"),
                balance=raw.get("balance", "-"),
                overlap=raw.get("component_face_overlap", "-"),
                time=row.get("inference_ms", "-"),
                notes=row.get("error") or "",
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input", action="append", default=[], help="original image path (repeatable)"
    )
    parser.add_argument(
        "--face-box",
        action="append",
        type=_parse_face_box,
        default=[],
        help="normalized 'x,y,w,h' (repeatable; paired with --input by order)",
    )
    parser.add_argument("--manifest", default=None, help="JSON manifest with named cases")
    parser.add_argument(
        "--models", default=DEFAULT_MODELS, help=f"comma list (default {DEFAULT_MODELS})"
    )
    parser.add_argument("--output-dir", default="local-data/segmentation-eval")
    parser.add_argument(
        "--json-out", default=None, help="defaults to <output-dir>/segmentation-evaluation.json"
    )
    parser.add_argument("--background-color", default=DEFAULT_BACKGROUND_COLOR)
    parser.add_argument("--portrait-model-path", default=DEFAULT_MODNET_PATH)
    parser.add_argument("--portrait-model-sha256", default=None)
    parser.add_argument("--birefnet-repo", default="ZhengPeng7/BiRefNet")
    parser.add_argument("--sam2-repo", default="facebook/sam2.1-hiera-large")
    parser.add_argument("--rmbg2-repo", default="briaai/RMBG-2.0")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "mps", "cuda"])
    parser.add_argument("--markdown-out", default=None, help="optional markdown results table path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    json_out = (
        Path(args.json_out) if args.json_out else output_root / "segmentation-evaluation.json"
    )
    background_rgb = parse_background_color(args.background_color)
    cases = _collect_cases(args)
    if not cases:
        print("no cases provided (use --input/--face-box or --manifest)", file=sys.stderr)
        return 2

    device = _pick_device(args.device)
    model_keys = [key.strip() for key in args.models.split(",") if key.strip()]
    print(f"device={device} cases={len(cases)} models={model_keys}")

    results: list[dict[str, Any]] = []
    specs: list[dict[str, Any]] = []
    for key in model_keys:
        try:
            provider = _build_provider(key, args, device)
        except Exception as exc:
            spec = (
                _spec_for(key)
                if key in MODEL_CATALOG
                else ModelSpec(
                    key=key,
                    name=key,
                    repo="",
                    code_license="",
                    weights_license="",
                    commercial_use="",
                    source="",
                    runtime="",
                )
            )
            spec.license_notes = f"SKIPPED: {type(exc).__name__}: {exc}"
            specs.append(asdict(spec))
            for case in cases:
                results.append(
                    {
                        "case": case.name,
                        "model": key,
                        "status": "SKIPPED",
                        "error": f"{type(exc).__name__}: {exc}",
                        "raw_integrity": None,
                    }
                )
            continue

        specs.append(asdict(provider.spec))
        for case in cases:
            print(f"  evaluating case={case.name} model={key}")
            results.append(_evaluate_case_model(case, provider, output_root, background_rgb))

    report = {
        "schema": EVAL_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "integrity_version": MATTE_INTEGRITY_VERSION,
        "refinement_version": MATTE_REFINEMENT_VERSION,
        "crop_version": CROP_VERSION,
        "background_color": args.background_color,
        "device": device,
        "models": specs,
        "cases": [
            {
                "name": case.name,
                "image": str(case.image_path),
                "face_box": list(case.face_box) if case.face_box else None,
                "notes": case.notes,
                "width": None,
                "height": None,
            }
            for case in cases
        ],
        "results": results,
    }
    json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {json_out}")

    if args.markdown_out:
        _write_markdown_table(results, Path(args.markdown_out))
        print(f"wrote {args.markdown_out}")

    failures = sum(1 for row in results if row.get("status") in {"ERROR", "SKIPPED"})
    return 1 if failures == len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
