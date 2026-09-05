/**
 * FaceDetectorProvider abstraction (M3 §8-9, §19, §72-75).
 *
 * Business/capture components depend only on this interface, never on MediaPipe internals. Later
 * detectors (YuNet, RetinaFace, YOLO-face variant, custom bank-approved) can be swapped in without
 * touching capture logic. No plugin framework — one interface, one implementation (plus the
 * deterministic test stub).
 *
 * MediaPipe Face Detector is NOT a liveness/spoof detector; its confidence is only
 * "a face was detected" and must never populate liveness_score/spoof_probability/risk_score
 * (M3 §10).
 */

import type { FaceDetectionResult, FaceDetectorInfo } from '../types/face'

export type FaceDetectorProviderState =
  'NOT_INITIALIZED' | 'LOADING' | 'READY' | 'ERROR' | 'DISPOSED'

export interface FaceDetectorProvider {
  readonly info: FaceDetectorInfo
  readonly state: FaceDetectorProviderState
  initialize(): Promise<void>
  detect(image: CanvasImageSource, timestampMs?: number): Promise<FaceDetectionResult>
  dispose(): void
}
