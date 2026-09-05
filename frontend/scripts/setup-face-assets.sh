#!/usr/bin/env bash
# Controlled face-model asset provisioning (M3 §11-12).
#
# Downloads the MediaPipe face-detector model, verifies its SHA-256 against the pinned hash in
# model-assets/manifest.json, then copies the verified model + the MediaPipe WASM runtime into
# git-ignored local paths served by the frontend.
#
# If manifest.sha256 is empty (pending-pin), the script refuses to place the model and prints the
# computed hash so a maintainer can pin it after confirming the source. An unverified downloaded
# model is never executed.
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$FRONTEND_DIR/model-assets/manifest.json"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
TASK_PATH="$FRONTEND_DIR/model-assets/face_detector.task"
WASM_SRC="$FRONTEND_DIR/node_modules/@mediapipe/tasks-vision/wasm"
WASM_DST="$FRONTEND_DIR/public/mediapipe-wasm"

if ! command -v node >/dev/null 2>&1; then
  echo "node is required" >&2
  exit 1
fi

pin_sha() {
  node -e 'const m=require(process.argv[1]); process.stdout.write(m.model.sha256 || "")' "$MANIFEST"
}

PIN="$(pin_sha)"

if [[ -z "$PIN" ]]; then
  echo "manifest.json sha256 is not pinned yet." >&2
  echo "Set manifest.sha256 after confirming the upstream source, or use:" >&2
  echo "  curl -sL '$MODEL_URL' | shasum -a 256" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TMP_MODEL="$TMP/face_detector.task"

echo "Downloading model..."
curl -sL "$MODEL_URL" -o "$TMP_MODEL"

COMPUTED="$(shasum -a 256 "$TMP_MODEL" | awk '{print $1}')"
echo "Computed SHA-256: $COMPUTED"
if [[ "$COMPUTED" != "$PIN" ]]; then
  echo "ERROR: SHA-256 mismatch. Expected $PIN, got $COMPUTED." >&2
  exit 1
fi

mkdir -p "$(dirname "$TASK_PATH")"
cp "$TMP_MODEL" "$TASK_PATH"
echo "Verified model placed at $TASK_PATH"

if [[ -d "$WASM_SRC" ]]; then
  mkdir -p "$WASM_DST"
  cp "$WASM_SRC"/*.js "$WASM_SRC"/*.wasm "$WASM_DST/"
  echo "MediaPipe WASM copied to $WASM_DST"
else
  echo "WARNING: @mediapipe/tasks-vision not installed; skipping WASM copy (npm ci first)." >&2
fi

echo "Model assets ready."