# Face model assets

This directory documents and provisions the MediaPipe face-detector model used by M3
(`frontend/src/features/capture/quality/face/MediaPipeFaceDetector.ts`).

**The model binary is NOT committed to this repository.** It is downloaded during developer setup
into a git-ignored path. The repo contains only the manifest and this documentation.

## Provenance

| Field         | Value                                                                                                                          |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Model         | MediaPipe Face Detector (short-range)                                                                                          |
| Upstream      | `https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite` |
| Tasks library | `@mediapipe/tasks-vision` (see `manifest.json`)                                                                                |
| License       | Apache-2.0                                                                                                                     |

## Setup

```bash
cd frontend
./scripts/setup-face-assets.sh
```

The script:

1. Downloads the model to a temporary location.
2. Computes its SHA-256.
3. **Verifies against the pinned hash in `manifest.json`.** If `manifest.sha256` is empty
   (`pending-pin`), the script refuses to place the model and prints the computed hash so a
   maintainer can pin it _after confirming the source_ — an unverified downloaded model is never
   executed.
4. Copies the verified model to `frontend/model-assets/face_detector.task` (git-ignored).
5. Copies the MediaPipe WASM runtime from `node_modules/@mediapipe/tasks-vision/wasm` to
   `frontend/public/mediapipe-wasm` (git-ignored) so the provider loads assets from the
   LivePhoto-controlled origin — never a public CDN at inference time.

## Model integrity (M3 §12)

- Download → compute SHA-256 → verify against the pinned expected hash → place in the approved
  local path. Do not run an unverified model.
- The pinned hash is recorded in `manifest.json`; updating the model requires updating the pin and
  re-verification.

## Local hosting

- Model path served at `/model-assets/face_detector.task`.
- WASM served at `/mediapipe-wasm/*`.
- In production these are served from the LivePhoto-controlled origin (bank-controlled hosting);
  external CDN fetches are not permitted for production inference.

## Update procedure

1. Download the new model artifact from an approved upstream source.
2. Compute its SHA-256.
3. Update `manifest.json` (`version`, `sha256`, `upstream_source` as needed).
4. Re-run `scripts/setup-face-assets.sh`; confirm the verified hash matches the pin.
5. Run the manual real-model smoke test (optional, tagged in `quality/tests`).

## Security implications

- Only pinned, source-verified model artifacts are used; a tampered model is detected via the
  SHA-256 mismatch and rejected.
- The face detector is NOT a liveness/spoof detector (M3 §10) and its output never populates
  liveness/spoof/risk scores.
- Model inference is local in the browser; no image ever leaves the device during M3.
