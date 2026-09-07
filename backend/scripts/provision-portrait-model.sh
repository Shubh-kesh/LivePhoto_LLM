#!/usr/bin/env bash
# Provision the backend portrait-matting model (MODNet photographic portrait matting, ONNX).
#
# Downloads the pinned, official MODNet weights (Apache-2.0) from a public Hugging Face mirror of
# the ZHKKKe/MODNet project and verifies the SHA-256. The asset is written to a git-ignored
# directory (backend/model-assets/). No weights are committed to git; LivePhoto never downloads
# model weights per-request (M5.7 §51-53, §110).
#
# Usage:
#   ./backend/scripts/provision-portrait-model.sh
#
# Set PORTRAIT_MODEL_PATH=./model-assets/modnet_photographic_portrait_matting.onnx when running
# the backend so the portrait processor uses this model.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST_DIR="$REPO_ROOT/backend/model-assets"
DEST="$DEST_DIR/modnet_photographic_portrait_matting.onnx"

URL="https://huggingface.co/DavG25/modnet-pretrained-models/resolve/main/models/modnet_photographic_portrait_matting.onnx"

# SHA-256 of the pinned model asset (verified on download).
EXPECTED_SHA256="07c308cf0fc7e6e8b2065a12ed7fc07e1de8febb7dc7839d7b7f15dd66584df9"

mkdir -p "$DEST_DIR"

if [[ -f "$DEST" ]]; then
  ACTUAL="$(shasum -a 256 "$DEST" | awk '{print $1}')"
  if [[ "$ACTUAL" == "$EXPECTED_SHA256" ]]; then
    echo "portrait model already provisioned and verified: $DEST"
    exit 0
  fi
  echo "existing model hash mismatch; re-downloading"
fi

echo "downloading MODNet photographic portrait matting ONNX..."
curl -sL --fail -o "$DEST" "$URL"

ACTUAL="$(shasum -a 256 "$DEST" | awk '{print $1}')"
if [[ "$ACTUAL" != "$EXPECTED_SHA256" ]]; then
  echo "error: SHA-256 mismatch" >&2
  echo "  expected: $EXPECTED_SHA256" >&2
  echo "  actual:   $ACTUAL" >&2
  rm -f "$DEST"
  exit 1
fi

echo "provisioned: $DEST"
echo "sha256: $ACTUAL"
echo
echo "run the backend with PORTRAIT_MODEL_PATH=$DEST (relative to backend/ CWD is fine)."