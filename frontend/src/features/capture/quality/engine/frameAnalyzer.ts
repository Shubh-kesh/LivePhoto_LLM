/**
 * Frame analyzer (M3 §28-29, §41-46).
 *
 * Produces a FrameQualityAssessment for one image source (live video frame or a burst frame).
 * The analysis buffer is transient and original capture data is never modified.
 */

import { qualityConfig, type QualityConfig } from '../config/qualityConfig'
import { QualityError } from '../errors'
import { buildAnalysisBuffer, sourceDimensions } from '../metrics/analysisImage'
import type { AnalysisBuffer } from '../metrics/types'
import { computeContrast } from '../metrics/contrast'
import { computeExposure } from '../metrics/luminance'
import { computeSharpness } from '../metrics/sharpness'
import type { FaceDetectorProvider } from '../face/FaceDetectorProvider'
import { faceCenterOffset, faceCoverageRatio } from '../face/faceGeometry'
import type { FaceMetrics } from '../types/face'
import type {
  FrameDisposition,
  FrameQualityAssessment,
  QualityMetricResult,
  QualityReasonCode,
} from '../types/quality'
import { deriveReasonCodes, computeComponentScores, makeMetricResult } from './qualityEngine'

export interface AnalyzeFrameOptions {
  source: CanvasImageSource
  detector: FaceDetectorProvider
  frameId: string
  sequence: number
  config?: QualityConfig
  buildBuffer?: (source: CanvasImageSource, maxDimension?: number) => AnalysisBuffer
  now?: () => number
}

export async function analyzeFrame(options: AnalyzeFrameOptions): Promise<FrameQualityAssessment> {
  const config = options.config ?? qualityConfig
  const now = options.now ?? (() => performance.now())
  const buildBuffer = options.buildBuffer ?? buildAnalysisBuffer
  const started = now()

  const dimensions = safeSourceDimensions(options.source)
  let analysisBuffer: AnalysisBuffer | null = null
  let analysisIssue: 'QUALITY_ANALYSIS_ERROR' | null = null
  try {
    analysisBuffer = buildBuffer(options.source, config.analysis.maxAnalysisDimension)
  } catch {
    analysisIssue = 'QUALITY_ANALYSIS_ERROR'
  }

  const exposure = analysisBuffer
    ? computeExposure(analysisBuffer, {
        darkPixelThreshold: config.exposure.darkPixelThreshold,
        brightPixelThreshold: config.exposure.brightPixelThreshold,
      })
    : { meanLuminance: 0, darkPixelRatio: 0, brightPixelRatio: 0 }
  const contrast = analysisBuffer ? computeContrast(analysisBuffer) : 0
  const sharpness = analysisBuffer ? computeSharpness(analysisBuffer) : 0

  let face: FaceMetrics
  let faceIssue = false
  try {
    const result = await options.detector.detect(options.source)
    face = buildFaceMetrics(result.detections)
  } catch {
    face = { count: 0 }
    faceIssue = true
  }

  // A technical failure must never become an image-quality classification (M3 §114-115): skip
  // pixel/face-based reason derivation when analysis could not complete.
  const reasonCodes: QualityReasonCode[] =
    analysisIssue || faceIssue
      ? []
      : deriveReasonCodes(dimensions, exposure, contrast, sharpness, face, config)
  if (analysisIssue) reasonCodes.push('QUALITY_ANALYSIS_ERROR')
  if (faceIssue) reasonCodes.push('FACE_ANALYSIS_UNAVAILABLE')

  const scores = computeComponentScores(exposure, contrast, sharpness, face, config)
  const metricResults = buildMetricResults(dimensions, exposure, contrast, sharpness, face, config)

  const disposition: FrameDisposition =
    analysisIssue || faceIssue
      ? 'ANALYSIS_UNAVAILABLE'
      : reasonCodes.some((r) => r !== 'FACE_OFF_CENTER')
        ? 'INELIGIBLE'
        : 'ELIGIBLE'

  return {
    frameId: options.frameId,
    sequence: options.sequence,
    configVersion: config.configVersion,
    dimensions: {
      width: dimensions.width,
      height: dimensions.height,
      pixelCount: dimensions.width * dimensions.height,
    },
    face,
    exposure,
    contrast: { rawValue: contrast },
    sharpness: { rawValue: sharpness },
    scores,
    metricResults,
    reasonCodes,
    disposition,
    analysisTimeMs: now() - started,
  }
}

function safeSourceDimensions(source: CanvasImageSource): { width: number; height: number } {
  try {
    return sourceDimensions(source)
  } catch {
    return { width: 0, height: 0 }
  }
}

function buildFaceMetrics(detections: import('../types/face').FaceDetection[]): FaceMetrics {
  if (detections.length === 0) return { count: 0 }
  if (detections.length > 1) return { count: detections.length }
  const detection = detections[0]
  const coverageRatio = faceCoverageRatio(detection.normalizedBoundingBox)
  const centerOffset = faceCenterOffset(detection.normalizedBoundingBox)
  return {
    count: 1,
    detectionConfidence: detection.confidence,
    boundingBox: detection.boundingBox,
    normalizedBoundingBox: detection.normalizedBoundingBox,
    coverageRatio,
    centerOffset,
  }
}

function buildMetricResults(
  dimensions: { width: number; height: number },
  exposure: { meanLuminance: number; darkPixelRatio: number; brightPixelRatio: number },
  contrast: number,
  sharpness: number,
  face: FaceMetrics,
  config: QualityConfig,
): QualityMetricResult[] {
  const results: QualityMetricResult[] = []

  const resolutionOk =
    dimensions.width >= config.resolution.minWidth &&
    dimensions.height >= config.resolution.minHeight
  results.push(
    makeMetricResult(
      'resolution',
      Math.min(dimensions.width, dimensions.height),
      0,
      Math.min(config.resolution.minWidth, config.resolution.minHeight),
      resolutionOk,
    ),
  )

  if (face.count === 1 && face.coverageRatio !== undefined && face.centerOffset !== undefined) {
    results.push(
      makeMetricResult(
        'face_coverage',
        face.coverageRatio,
        0,
        config.face.minFaceCoverage,
        face.coverageRatio >= config.face.minFaceCoverage &&
          face.coverageRatio <= config.face.maxFaceCoverage,
      ),
    )
    results.push(
      makeMetricResult(
        'face_center_distance',
        face.centerOffset.distance,
        0,
        Math.sqrt(config.face.maxCenterOffsetX ** 2 + config.face.maxCenterOffsetY ** 2),
        face.centerOffset.distance <=
          Math.sqrt(config.face.maxCenterOffsetX ** 2 + config.face.maxCenterOffsetY ** 2),
      ),
    )
  }

  results.push(
    makeMetricResult(
      'sharpness',
      sharpness,
      Math.min(1, sharpness / config.sharpness.blurThreshold),
      config.sharpness.blurThreshold,
      sharpness >= config.sharpness.blurThreshold,
    ),
    makeMetricResult(
      'mean_luminance',
      exposure.meanLuminance,
      0,
      config.exposure.minMeanLuminance,
      exposure.meanLuminance >= config.exposure.minMeanLuminance &&
        exposure.meanLuminance <= config.exposure.maxMeanLuminance,
    ),
    makeMetricResult(
      'contrast',
      contrast,
      Math.min(1, contrast / config.contrast.minContrast),
      config.contrast.minContrast,
      contrast >= config.contrast.minContrast,
    ),
  )

  return results
}

export function isQualityError(value: unknown): value is QualityError {
  return value instanceof QualityError
}
