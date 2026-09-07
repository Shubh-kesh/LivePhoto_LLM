#!/usr/bin/env bash
# Controlled face-model asset provisioning (M3 §11-12, M5.7 §21, §37).
#
# Downloads the MediaPipe face-detector model AND the Face Landmarker (eye-state) model, verifies
# their SHA-256 against the pinned hashes in model-assets/manifest.json, then copies the verified
# models + the MediaPipe WASM runtime into git-ignored local paths served by the frontend.
#
# If a manifest.sha256 is empty (pending-pin), the script refuses to place that model and prints
# the computed hash so a maintainer can pin it after confirming the source. An unverified
# downloaded model is never executed.
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$FRONTEND_DIR/model-assets/manifest.json"
WASM_SRC="$FRONTEND_DIR/node_modules/@mediapipe/tasks-vision/wasm"
WASM_DST="$FRONTEND_DIR/public/mediapipe-wasm"

if ! command -v node >/dev/null 2>&1; then
  echo "node is required" >&2
  exit 1
fi

pin_sha() {
  node -e 'const m=require(process.argv[1]); process.stdout.write(m[process.argv[2]].sha256 || "")' "$MANIFEST" "$1"
}

provision() {
  local manifest_key="$1"
  local url="$2"
  local dest="$3"
  local pin computed tmp_model

  pin="$(pin_sha "$manifest_key")"
  if [[ -z "$pin" ]]; then
    echo "manifest.json [$manifest_key].sha256 is not pinned yet." >&2
    echo "Set it after confirming the upstream source, or use:" >&2
    echo "  curl -sL '$url' | shasum -a 256" >&2
    return 1
  fi

  tmp_model="$(mktemp)"
  trap 'rm -f "$tmp_model"' RETURN
  echo "Downloading $manifest_key..."
  curl -sL --fail "$url" -o "$tmp_model"

  computed="$(shasum -a 256 "$tmp_model" | awk '{print $1}')"
  echo "Computed SHA-256 ($manifest_key): $computed"
  if [[ "$computed" != "$pin" ]]; then
    echo "ERROR: SHA-256 mismatch for $manifest_key. Expected $pin, got $computed." >&2
    return 1
  fi

  mkdir -p "$(dirname "$dest")"
  cp "$tmp_model" "$dest"
  echo "Verified model placed at $dest"
}

provision \
  "model" \
  "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite" \
  "$FRONTEND_DIR/model-assets/face_detector.task"

provision \
  "eye_state_model" \
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" \
  "$FRONTEND_DIR/model-assets/face_landmarker.task"

if [[ -d "$WASM_SRC" ]]; then
  mkdir -p "$WASM_DST"
  cp "$WASM_SRC"/*.js "$WASM_SRC"/*.wasm "$WASM_DST/"
  echo "MediaPipe WASM copied to $WASM_DST"
else
  echo "WARN: @mediapipe/tasks-vision WASM not found at $WASM_SRC; run npm ci first." >&2
fi

echo "Face model assets provisioned."