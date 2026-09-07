/**
 * Face-participation heuristics (M5.7 §28-30, §89-90).
 *
 * Capture quality distinguishes a genuine second participating foreground person from irrelevant
 * background people. "Participating" faces are substantial and near the capture region:
 *   - normalized face area >= the primary minFaceCoverage (substantial)
 *   - face center within a region around the frame center (1.5x the primary centering bound)
 *   - detection confidence >= minDetectionConfidence
 *
 * This is capture-quality / UX logic — NOT liveness, identity, or demographics. Small peripheral
 * faces (a distant person in the background) never force MULTIPLE_FACES; portrait matting removes
 * them. Never infer age/gender/ethnicity.
 */

import type { QualityConfig } from '../config/qualityConfig'
import type { FaceDetection } from '../types/face'
import { faceCenterOffset, faceCoverageRatio } from './faceGeometry'

/** Participating faces may be up to 1.5x the primary centering bound from the frame center. */
const PARTICIPATING_CENTER_MULTIPLIER = 1.5

export function participatingFaceCount(detections: FaceDetection[], config: QualityConfig): number {
  const { minDetectionConfidence, minFaceCoverage, maxCenterOffsetX, maxCenterOffsetY } =
    config.face
  const maxDistance =
    Math.sqrt(maxCenterOffsetX ** 2 + maxCenterOffsetY ** 2) * PARTICIPATING_CENTER_MULTIPLIER
  let count = 0
  for (const detection of detections) {
    if (detection.confidence < minDetectionConfidence) continue
    const box = detection.normalizedBoundingBox
    if (faceCoverageRatio(box) < minFaceCoverage) continue
    if (faceCenterOffset(box).distance > maxDistance) continue
    count += 1
  }
  return count
}

/** Largest participating face; falls back to the largest overall detection (M5.7 §58). */
export function primaryFaceDetection(
  detections: FaceDetection[],
  config: QualityConfig,
): FaceDetection | null {
  const candidates = detections.filter(
    (detection) =>
      detection.confidence >= config.face.minDetectionConfidence &&
      faceCoverageRatio(detection.normalizedBoundingBox) >= config.face.minFaceCoverage,
  )
  const pool = candidates.length > 0 ? candidates : detections
  if (pool.length === 0) return null
  return pool.reduce((largest, current) =>
    faceCoverageRatio(current.normalizedBoundingBox) >
    faceCoverageRatio(largest.normalizedBoundingBox)
      ? current
      : largest,
  )
}
