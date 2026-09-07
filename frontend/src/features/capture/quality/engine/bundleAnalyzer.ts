/**
 * Bundle analyzer (M3 §51-55, §59, §83-86).
 *
 * Analyzes EVERY successfully captured frame (not just the M2 representative), decodes one frame
 * at a time and releases the bitmap immediately (no unbounded pixel buffers), aggregates reasons,
 * and selects the quality-based representative. Non-selected frames are NOT discarded (M4+
 * validators may need them) — only the temporary decode buffers are released.
 */

import { qualityConfig, type QualityConfig } from '../config/qualityConfig'
import type { CaptureBundle } from '../../types/capture'
import type { FaceDetectorProvider } from '../face/FaceDetectorProvider'
import type { EyeStateEvaluatorProvider } from '../eye/EyeStateEvaluatorProvider'
import type {
  FrameQualityAssessment,
  BundleQualityAssessment,
  QualityReasonCode,
} from '../types/quality'
import { analyzeFrame, type AnalyzeFrameOptions } from './frameAnalyzer'
import { selectEligibleFrame } from './frameRanking'

export interface DecodedImage {
  image: CanvasImageSource
  close: () => void
}

export async function decodeFrameImage(blob: Blob): Promise<DecodedImage> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(blob)
    return { image: bitmap, close: () => bitmap.close() }
  }
  // Fallback: <img> + object URL drawn onto a canvas (M3 §55).
  const url = URL.createObjectURL(blob)
  try {
    const image = new Image()
    image.src = url
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('image decode failed'))
    })
    const canvas = document.createElement('canvas')
    canvas.width = image.naturalWidth
    canvas.height = image.naturalHeight
    const context = canvas.getContext('2d')
    if (!context) throw new Error('canvas context unavailable')
    context.drawImage(image, 0, 0)
    return { image: canvas, close: () => undefined }
  } finally {
    URL.revokeObjectURL(url)
  }
}

export interface AnalyzeBundleOptions {
  detector: FaceDetectorProvider
  eyeEvaluator?: EyeStateEvaluatorProvider
  config?: QualityConfig
  analyzeFrame?: (options: AnalyzeFrameOptions) => Promise<FrameQualityAssessment>
  decodeFrameImage?: (blob: Blob) => Promise<DecodedImage>
  now?: () => number
}

function unavailableAssessment(
  bundle: CaptureBundle,
  sequence: number,
  config: QualityConfig,
): FrameQualityAssessment {
  return {
    frameId: bundle.frames[sequence]?.id ?? `unavailable-${sequence}`,
    sequence,
    configVersion: config.configVersion,
    dimensions: { width: 0, height: 0, pixelCount: 0 },
    face: { count: 0 },
    exposure: { meanLuminance: 0, darkPixelRatio: 0, brightPixelRatio: 0 },
    contrast: { rawValue: 0 },
    sharpness: { rawValue: 0 },
    scores: { exposure: 0, contrast: 0, sharpness: 0, overallQuality: 0 },
    metricResults: [],
    reasonCodes: ['QUALITY_ANALYSIS_ERROR'],
    disposition: 'ANALYSIS_UNAVAILABLE',
    analysisTimeMs: 0,
  }
}

export async function analyzeBundle(
  bundle: CaptureBundle,
  options: AnalyzeBundleOptions,
): Promise<BundleQualityAssessment> {
  const config = options.config ?? qualityConfig
  const now = options.now ?? (() => performance.now())
  const analyze = options.analyzeFrame ?? analyzeFrame
  const decode = options.decodeFrameImage ?? decodeFrameImage
  const started = now()

  const frames: FrameQualityAssessment[] = []
  for (const frame of bundle.frames) {
    let decoded: DecodedImage | null = null
    try {
      decoded = await decode(frame.blob)
      const assessment = await analyze({
        source: decoded.image,
        detector: options.detector,
        eyeEvaluator: options.eyeEvaluator,
        frameId: frame.id,
        sequence: frame.sequence,
        config,
        now,
      })
      frames.push(assessment)
    } catch {
      frames.push(unavailableAssessment(bundle, frame.sequence, config))
    } finally {
      decoded?.close()
    }
  }

  const eligibleFrameIds = frames.filter((f) => f.disposition === 'ELIGIBLE').map((f) => f.frameId)
  const unavailableCount = frames.filter((f) => f.disposition === 'ANALYSIS_UNAVAILABLE').length
  const reasonCodes = aggregateReasons(frames, config)

  let disposition: BundleQualityAssessment['disposition']
  if (unavailableCount === bundle.frames.length) {
    disposition = 'ANALYSIS_UNAVAILABLE'
  } else if (eligibleFrameIds.length >= config.bundle.minimumEligibleFrames) {
    disposition = 'QUALITY_READY'
  } else {
    disposition = 'QUALITY_RETRY'
  }

  const selection = disposition === 'QUALITY_READY' ? selectEligibleFrame(frames) : undefined

  return {
    captureId: bundle.captureId,
    captureConfigVersion: bundle.captureConfigVersion,
    qualityConfigVersion: config.configVersion,
    frames,
    eligibleFrameIds,
    selectedFrameId: selection?.selectedId ?? undefined,
    selectionAlgorithmVersion: selection?.algorithmVersion ?? '',
    selectionScore: selection?.selectionScore,
    disposition,
    reasonCodes,
    totalAnalysisTimeMs: now() - started,
  }
}

/**
 * Reason aggregation (M3 §85): include hard blockers that are common across the burst (appear in
 * >= aggregationMinimum frames). If a burst has no eligible frames and no common reason, fall back
 * to the single most frequent reason so the retry guidance is never empty.
 */
export function aggregateReasons(
  assessments: FrameQualityAssessment[],
  config: QualityConfig,
): QualityReasonCode[] {
  const counts = new Map<QualityReasonCode, number>()
  for (const assessment of assessments) {
    for (const reason of assessment.reasonCodes) {
      counts.set(reason, (counts.get(reason) ?? 0) + 1)
    }
  }
  const aggregationMinimum = config.bundle.reasonAggregationMinimum
  const common = [...counts.entries()]
    .filter(([, count]) => count >= aggregationMinimum)
    .sort((a, b) => b[1] - a[1])
    .map(([reason]) => reason)

  if (common.length > 0) return common

  const eligibleCount = assessments.filter((a) => a.disposition === 'ELIGIBLE').length
  if (eligibleCount === 0) {
    const mostFrequent = [...counts.entries()].sort((a, b) => b[1] - a[1])
    if (mostFrequent.length > 0) return [mostFrequent[0][0]]
  }
  return []
}
