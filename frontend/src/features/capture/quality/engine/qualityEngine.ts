/**
 * Quality scoring and reason-code derivation (M3 §40-50, §113-115).
 *
 * - `overallQualityScore` = minimum of applicable component scores (weakest-dimension approach,
 *   PROVISIONAL, M3 §49). It is an interpretable 0..1 quality indicator — NOT a probability,
 *   NOT liveness confidence, NOT spoof probability (M3 §48).
 * - `normalized_score` is a deterministic normalization, NOT a calibrated probability (M3 §42).
 * - A technical failure is NEVER converted into an image-quality classification (M3 §114-115).
 */

import type {
  ExposureMetrics,
  QualityMetricResult,
  QualityReasonCode,
  QualityScores,
} from '../types/quality'
import type { FaceMetrics } from '../types/face'
import type { QualityConfig } from '../config/qualityConfig'
import { clamp01 } from '../face/faceGeometry'

export const HARD_BLOCKER_REASONS: ReadonlySet<QualityReasonCode> = new Set([
  'NO_FACE',
  'MULTIPLE_FACES',
  'FACE_TOO_SMALL',
  'FACE_TOO_LARGE',
  'BLURRED',
  'UNDEREXPOSED',
  'OVEREXPOSED',
  'LOW_CONTRAST',
  'RESOLUTION_TOO_LOW',
  'FACE_ANALYSIS_UNAVAILABLE',
  'QUALITY_ANALYSIS_ERROR',
])

/** Deterministic, bounded (0..1) normalization functions. */

export function normalizeExposure(metrics: ExposureMetrics, config: QualityConfig): number {
  const { minMeanLuminance, maxMeanLuminance, maxDarkPixelRatio, maxBrightPixelRatio } =
    config.exposure
  const mean = metrics.meanLuminance
  let meanScore = 1
  if (mean < minMeanLuminance) meanScore = clamp01(mean / minMeanLuminance)
  else if (mean > maxMeanLuminance) meanScore = clamp01((1 - mean) / (1 - maxMeanLuminance))
  const darkPenalty = clamp01(metrics.darkPixelRatio / maxDarkPixelRatio)
  const brightPenalty = clamp01(metrics.brightPixelRatio / maxBrightPixelRatio)
  return Math.min(meanScore, 1 - darkPenalty, 1 - brightPenalty)
}

export function normalizeContrast(rawValue: number, config: QualityConfig): number {
  return clamp01(rawValue / config.contrast.minContrast)
}

export function normalizeSharpness(rawValue: number, config: QualityConfig): number {
  return clamp01(rawValue / config.sharpness.blurThreshold)
}

export function normalizeFace(face: FaceMetrics, config: QualityConfig): number {
  if (face.count !== 1 || face.coverageRatio === undefined || face.centerOffset === undefined) {
    return 0
  }
  const {
    minFaceCoverage,
    maxFaceCoverage,
    maxCenterOffsetX,
    maxCenterOffsetY,
    minDetectionConfidence,
  } = config.face

  let coverageScore = 1
  if (face.coverageRatio < minFaceCoverage)
    coverageScore = clamp01(face.coverageRatio / minFaceCoverage)
  else if (face.coverageRatio > maxFaceCoverage) {
    coverageScore = clamp01((1 - face.coverageRatio) / (1 - maxFaceCoverage))
  }

  const maxDistance = Math.sqrt(maxCenterOffsetX ** 2 + maxCenterOffsetY ** 2)
  const centerScore = maxDistance > 0 ? clamp01(1 - face.centerOffset.distance / maxDistance) : 1

  const confidence = face.detectionConfidence ?? 0
  const confidenceScore = clamp01(confidence / minDetectionConfidence)

  return Math.min(coverageScore, centerScore, confidenceScore)
}

export function computeComponentScores(
  exposure: ExposureMetrics,
  contrast: number,
  sharpness: number,
  face: FaceMetrics,
  config: QualityConfig,
): QualityScores {
  const exposureScore = normalizeExposure(exposure, config)
  const contrastScore = normalizeContrast(contrast, config)
  const sharpnessScore = normalizeSharpness(sharpness, config)
  const faceScore = normalizeFace(face, config)

  const applicable = [exposureScore, contrastScore, sharpnessScore]
  if (face.count === 1) applicable.push(faceScore)
  const overallQuality = applicable.length > 0 ? Math.min(...applicable) : 0

  return {
    face: face.count === 1 ? faceScore : undefined,
    exposure: exposureScore,
    contrast: contrastScore,
    sharpness: sharpnessScore,
    overallQuality,
  }
}

export function deriveReasonCodes(
  dimensions: { width: number; height: number },
  exposure: ExposureMetrics,
  contrast: number,
  sharpness: number,
  face: FaceMetrics,
  config: QualityConfig,
): QualityReasonCode[] {
  const reasons: QualityReasonCode[] = []

  if (
    dimensions.width < config.resolution.minWidth ||
    dimensions.height < config.resolution.minHeight
  ) {
    reasons.push('RESOLUTION_TOO_LOW')
  }

  if (face.count === 0) {
    reasons.push('NO_FACE')
  } else {
    // MULTIPLE_FACES reflects *participating* foreground faces, not incidental background faces
    // (M5.7 §28-30): a small peripheral/profile face never forces a rejection.
    const participating = face.participatingCount ?? face.count
    if (participating >= 2) {
      reasons.push('MULTIPLE_FACES')
    } else {
      const { minFaceCoverage, maxFaceCoverage, maxCenterOffsetX, maxCenterOffsetY } = config.face
      if (face.coverageRatio !== undefined && face.coverageRatio < minFaceCoverage) {
        reasons.push('FACE_TOO_SMALL')
      }
      if (face.coverageRatio !== undefined && face.coverageRatio > maxFaceCoverage) {
        reasons.push('FACE_TOO_LARGE')
      }
      if (face.centerOffset !== undefined) {
        const maxDistance = Math.sqrt(maxCenterOffsetX ** 2 + maxCenterOffsetY ** 2)
        if (face.centerOffset.distance > maxDistance) {
          reasons.push('FACE_OFF_CENTER')
        }
      }
    }
  }

  if (sharpness < config.sharpness.blurThreshold) reasons.push('BLURRED')

  const { minMeanLuminance, maxMeanLuminance, maxDarkPixelRatio, maxBrightPixelRatio } =
    config.exposure
  if (exposure.meanLuminance < minMeanLuminance || exposure.darkPixelRatio > maxDarkPixelRatio) {
    reasons.push('UNDEREXPOSED')
  }
  if (
    exposure.meanLuminance > maxMeanLuminance ||
    exposure.brightPixelRatio > maxBrightPixelRatio
  ) {
    reasons.push('OVEREXPOSED')
  }

  if (contrast < config.contrast.minContrast) reasons.push('LOW_CONTRAST')

  return reasons
}

export function isHardBlocker(reason: QualityReasonCode): boolean {
  return HARD_BLOCKER_REASONS.has(reason)
}

export function makeMetricResult(
  metric: string,
  rawValue: number,
  normalizedScore: number,
  threshold: number,
  acceptable: boolean,
): QualityMetricResult {
  return {
    metric,
    rawValue,
    normalizedScore,
    threshold,
    result: acceptable ? 'ACCEPTABLE' : 'UNACCEPTABLE',
  }
}
