/**
 * Quality analysis data contracts (M3).
 *
 * Quality results are preliminary UX/evidence signals in the browser (M3 §6). They are NOT
 * authoritative security results, and scores are NOT probabilities:
 *   - `normalized_score` is a deterministic normalization, NOT a calibrated probability.
 *   - `overallQualityScore` is an interpretable 0..1 quality indicator, NOT liveness confidence
 *     and NOT spoof probability (M3 §48).
 */

import type { FaceMetrics } from './face'

export type QualityDisposition = 'QUALITY_READY' | 'QUALITY_RETRY' | 'ANALYSIS_UNAVAILABLE'

export type FrameDisposition = 'ELIGIBLE' | 'INELIGIBLE' | 'ANALYSIS_UNAVAILABLE'

export type QualityReasonCode =
  | 'NO_FACE'
  | 'MULTIPLE_FACES'
  | 'FACE_TOO_SMALL'
  | 'FACE_TOO_LARGE'
  | 'FACE_OFF_CENTER'
  | 'BLURRED'
  | 'UNDEREXPOSED'
  | 'OVEREXPOSED'
  | 'LOW_CONTRAST'
  | 'RESOLUTION_TOO_LOW'
  | 'FACE_ANALYSIS_UNAVAILABLE'
  | 'QUALITY_ANALYSIS_ERROR'

export interface ExposureMetrics {
  meanLuminance: number
  darkPixelRatio: number
  brightPixelRatio: number
}

export interface ContrastMetrics {
  rawValue: number
}

export interface SharpnessMetrics {
  rawValue: number
}

export interface QualityScores {
  face?: number
  exposure: number
  contrast: number
  sharpness: number
  overallQuality: number
}

export interface QualityMetricResult {
  metric: string
  rawValue: number
  normalizedScore: number
  threshold: number
  result: 'ACCEPTABLE' | 'UNACCEPTABLE'
}

export interface FrameQualityAssessment {
  frameId: string
  sequence: number
  configVersion: string
  dimensions: {
    width: number
    height: number
    pixelCount: number
  }
  face: FaceMetrics
  exposure: ExposureMetrics
  contrast: ContrastMetrics
  sharpness: SharpnessMetrics
  scores: QualityScores
  metricResults: QualityMetricResult[]
  reasonCodes: QualityReasonCode[]
  disposition: FrameDisposition
  analysisTimeMs: number
}

export interface BundleQualityAssessment {
  captureId: string
  captureConfigVersion: string
  qualityConfigVersion: string
  frames: FrameQualityAssessment[]
  eligibleFrameIds: string[]
  selectedFrameId?: string
  selectionAlgorithmVersion: string
  selectionScore?: number
  disposition: QualityDisposition
  reasonCodes: QualityReasonCode[]
  totalAnalysisTimeMs: number
}

export const FRAME_RANKING_VERSION = 'frame-ranking-v1'
