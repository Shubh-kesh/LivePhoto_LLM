#!/usr/bin/env bash
# Build the LivePhoto backend + frontend container images (M5.6 §76-77).
#
# Builds ONLY the two app images (no push, no Kubernetes/Helm). The MSSQL image is mirrored from
# the official Microsoft image separately (see infrastructure/docker/IMAGE_INVENTORY.md).
#
# Usage:
#   ./scripts/build-uat-images.sh --platform linux/amd64 --tag "$(git rev-parse --short HEAD)"
#   ./scripts/build-uat-images.sh --tag uat   # build for the host architecture
#
# Output: livephoto-backend:<tag>, livephoto-frontend:<tag>

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=""
PLATFORM=""

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) TAG="${2:-}"; shift 2 ;;
    --platform) PLATFORM="${2:-}"; shift 2 ;;
    *) echo "unknown option: $1"; usage ;;
  esac
done

if [[ -z "$TAG" ]]; then
  echo "error: --tag is required (e.g. --tag \"\$(git rev-parse --short HEAD)\")" >&2
  usage
fi

PLATFORM_ARGS=()
if [[ -n "$PLATFORM" ]]; then
  PLATFORM_ARGS+=(--platform "$PLATFORM")
fi

echo "==> Building livephoto-backend:${TAG} ${PLATFORM:+platform=${PLATFORM}}"
docker buildx build "${PLATFORM_ARGS[@]}" \
  -f "$REPO_ROOT/backend/Dockerfile" \
  -t "livephoto-backend:${TAG}" \
  "$REPO_ROOT/backend"

echo "==> Building livephoto-frontend:${TAG} ${PLATFORM:+platform=${PLATFORM}}"
docker buildx build "${PLATFORM_ARGS[@]}" \
  -f "$REPO_ROOT/frontend/Dockerfile" \
  -t "livephoto-frontend:${TAG}" \
  "$REPO_ROOT/frontend"

echo
echo "Built images:"
echo "  livephoto-backend:${TAG}"
echo "  livephoto-frontend:${TAG}"
echo
echo "Push only when deploying, e.g.:"
echo "  docker tag livephoto-backend:${TAG} <artifact-registry>/livephoto-backend:${TAG}"
echo "  docker tag livephoto-frontend:${TAG} <artifact-registry>/livephoto-frontend:${TAG}"
