/**
 * Face detection types (M3 §19-23).
 *
 * Detector output is normalized into our own types; MediaPipe objects never leak into React.
 * `confidence` is the detector's face-detection confidence, NOT a probability that the subject is
 * live/real/genuine (M3 §10, §23).
 */

export interface FaceBoundingBox {
  x: number
  y: number
  width: number
  height: number
}

export interface FaceKeypoint {
  x: number
  y: number
}

export interface FaceDetection {
  confidence: number
  boundingBox: FaceBoundingBox
  normalizedBoundingBox: FaceBoundingBox
  keypoints?: FaceKeypoint[]
}

export interface FaceDetectionResult {
  detections: FaceDetection[]
  imageWidth: number
  imageHeight: number
  inferenceTimeMs?: number
}

/** Aggregated per-frame face metrics used by the quality engine (M3 §21-25). */
export interface FaceMetrics {
  count: number
  detectionConfidence?: number
  boundingBox?: FaceBoundingBox
  normalizedBoundingBox?: FaceBoundingBox
  coverageRatio?: number
  centerOffset?: {
    dx: number
    dy: number
    distance: number
  }
}

/** Detector identity/versioning metadata (M3 §116-117). */
export interface FaceDetectorInfo {
  name: string
  version: string
  modelVersion: string
}
