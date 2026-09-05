/**
 * bundleAnalyzer tests (M3 §51-55, §59, §83-86). Injects deterministic decode + analyze fakes so
 * no canvas/ImageData/real model is required.
 */

import { describe, expect, it, vi } from 'vitest'

import { analyzeBundle } from '../engine/bundleAnalyzer'
import type { CaptureBundle } from '../../types/capture'
import type { FrameQualityAssessment, QualityReasonCode } from '../types/quality'
import { FakeFaceDetector } from '../../tests/qualityFakes'

const DETECTOR: FakeFaceDetector = new FakeFaceDetector()

function makeBundle(frameCount: number): CaptureBundle {
  return {
    captureId: 'capture-1',
    createdAt: '2026-01-01T00:00:00Z',
    captureConfigVersion: 'capture-v1',
    camera: { facingMode: 'user' },
    frames: Array.from({ length: frameCount }, (_, i) => ({
      id: `frame-${i}`,
      sequence: i,
      capturedAtMs: i,
      blob: new Blob(['x']),
      mimeType: 'image/jpeg',
      width: 640,
      height: 480,
      byteSize: 1,
    })),
    representativeFrameId: 'frame-0',
  }
}

interface AssessmentOverrides {
  disposition?: FrameQualityAssessment['disposition']
  overallQuality?: number
  confidence?: number
  centerDistance?: number
  reasons?: QualityReasonCode[]
}

function assessment(sequence: number, overrides: AssessmentOverrides = {}): FrameQualityAssessment {
  return {
    frameId: `frame-${sequence}`,
    sequence,
    configVersion: 'quality-v1',
    dimensions: { width: 640, height: 480, pixelCount: 640 * 480 },
    face: {
      count: 1,
      detectionConfidence: overrides.confidence ?? 0.95,
      coverageRatio: 0.3,
      centerOffset: { dx: 0, dy: 0, distance: overrides.centerDistance ?? 0 },
    },
    exposure: { meanLuminance: 0.5, darkPixelRatio: 0.05, brightPixelRatio: 0.05 },
    contrast: { rawValue: 0.2 },
    sharpness: { rawValue: 300 },
    scores: {
      face: 0.95,
      exposure: 0.95,
      contrast: 1,
      sharpness: 1,
      overallQuality: overrides.overallQuality ?? 0.9,
    },
    metricResults: [],
    reasonCodes: overrides.reasons ?? [],
    disposition: overrides.disposition ?? 'ELIGIBLE',
    analysisTimeMs: 1,
  }
}

function makeOptions(assessments: FrameQualityAssessment[]) {
  const closeSpy = vi.fn()
  const decodeFrameImage = vi.fn(async () => ({
    image: { width: 640, height: 480 } as unknown as CanvasImageSource,
    close: closeSpy,
  }))
  const analyzeFrame = vi.fn(async (opts: { frameId: string }) => {
    const found = assessments.find((a) => a.frameId === opts.frameId)
    if (!found) throw new Error('no assessment')
    return found
  })
  return { analyzeFrame, decodeFrameImage, closeSpy }
}

describe('analyzeBundle', () => {
  it('analyzes every frame, selects the best, and closes each decode', async () => {
    const bundle = makeBundle(8)
    const assessments = [
      assessment(0, { overallQuality: 0.5 }),
      assessment(1, { overallQuality: 0.99 }),
      assessment(2, { overallQuality: 0.98 }),
      ...Array.from({ length: 5 }, (_, i) => assessment(3 + i, { overallQuality: 0.9 })),
    ]
    const { analyzeFrame, decodeFrameImage, closeSpy } = makeOptions(assessments)
    const result = await analyzeBundle(bundle, {
      detector: DETECTOR,
      analyzeFrame,
      decodeFrameImage,
    })
    expect(analyzeFrame).toHaveBeenCalledTimes(8)
    expect(closeSpy).toHaveBeenCalledTimes(8)
    expect(result.eligibleFrameIds).toHaveLength(8)
    expect(result.selectedFrameId).toBe('frame-1')
    expect(result.disposition).toBe('QUALITY_READY')
    expect(result.selectionAlgorithmVersion).toBe('frame-ranking-v1')
    expect(result.qualityConfigVersion).toBe('quality-v1')
  })

  it('prefers a sharp later frame over a blurred middle frame', async () => {
    const bundle = makeBundle(8)
    const assessments = Array.from({ length: 8 }, (_, i) => assessment(i, { overallQuality: 0.5 }))
    assessments[6] = assessment(6, { overallQuality: 0.95 })
    const result = await analyzeBundle(bundle, { detector: DETECTOR, ...makeOptions(assessments) })
    expect(result.selectedFrameId).toBe('frame-6')
  })

  it('prefers good exposure over a sharp-but-badly-exposed frame', async () => {
    const bundle = makeBundle(8)
    const assessments = Array.from({ length: 8 }, (_, i) => assessment(i, { overallQuality: 0.85 }))
    assessments[5] = assessment(5, { overallQuality: 0.3 })
    const result = await analyzeBundle(bundle, { detector: DETECTOR, ...makeOptions(assessments) })
    expect(result.disposition).toBe('QUALITY_READY')
    expect(result.selectedFrameId).not.toBe('frame-5')
    // Among the equal-good frames, the deterministic tie-break picks the temporal center.
    expect(result.selectedFrameId).toBe('frame-3')
  })

  it('is deterministic for equal frames (earliest closest to center)', async () => {
    const bundle = makeBundle(8)
    const assessments = Array.from({ length: 8 }, (_, i) => assessment(i, { overallQuality: 0.9 }))
    const result = await analyzeBundle(bundle, { detector: DETECTOR, ...makeOptions(assessments) })
    expect(result.selectedFrameId).toBe('frame-3')
    const again = await analyzeBundle(bundle, { detector: DETECTOR, ...makeOptions(assessments) })
    expect(again.selectedFrameId).toBe('frame-3')
  })

  it('QUALITY_RETRY when too few eligible frames, aggregating common reasons', async () => {
    const bundle = makeBundle(8)
    const assessments = Array.from({ length: 8 }, (_, i) =>
      assessment(i, { disposition: 'INELIGIBLE', reasons: ['NO_FACE'], overallQuality: 0 }),
    )
    const result = await analyzeBundle(bundle, { detector: DETECTOR, ...makeOptions(assessments) })
    expect(result.disposition).toBe('QUALITY_RETRY')
    expect(result.eligibleFrameIds).toHaveLength(0)
    expect(result.reasonCodes).toContain('NO_FACE')
  })

  it('does not aggregate a reason seen in only one frame when enough frames are eligible', async () => {
    const bundle = makeBundle(8)
    const assessments = Array.from({ length: 8 }, (_, i) => assessment(i, { overallQuality: 0.9 }))
    assessments[4] = assessment(4, {
      disposition: 'INELIGIBLE',
      reasons: ['UNDEREXPOSED'],
      overallQuality: 0,
    })
    const result = await analyzeBundle(bundle, { detector: DETECTOR, ...makeOptions(assessments) })
    expect(result.disposition).toBe('QUALITY_READY')
    expect(result.reasonCodes).not.toContain('UNDEREXPOSED')
  })

  it('requires at least the minimum eligible frames', async () => {
    const bundle = makeBundle(8)
    const assessments = [
      assessment(0, { overallQuality: 0.9 }),
      assessment(1, { overallQuality: 0.9 }),
      ...Array.from({ length: 6 }, (_, i) =>
        assessment(2 + i, { disposition: 'INELIGIBLE', reasons: ['BLURRED'], overallQuality: 0 }),
      ),
    ]
    const result = await analyzeBundle(bundle, { detector: DETECTOR, ...makeOptions(assessments) })
    expect(result.disposition).toBe('QUALITY_RETRY')
    expect(result.reasonCodes).toContain('BLURRED')
  })

  it('ANALYSIS_UNAVAILABLE when every frame fails to decode', async () => {
    const bundle = makeBundle(8)
    const decode = vi.fn(async () => {
      throw new Error('decode failed')
    })
    const result = await analyzeBundle(bundle, { detector: DETECTOR, decodeFrameImage: decode })
    expect(result.disposition).toBe('ANALYSIS_UNAVAILABLE')
    expect(result.eligibleFrameIds).toHaveLength(0)
  })

  it('recovers when some frames fail to decode but enough succeed', async () => {
    const bundle = makeBundle(8)
    const assessments = Array.from({ length: 6 }, (_, i) => assessment(i, { overallQuality: 0.9 }))
    let decodeCalls = 0
    const decodeFrameImage = vi.fn(async () => {
      decodeCalls += 1
      if (decodeCalls > 6) throw new Error('decode failed')
      return { image: { width: 640, height: 480 } as unknown as CanvasImageSource, close: vi.fn() }
    })
    const analyzeFrame = vi.fn(async (opts: { frameId: string }) => {
      const found = assessments.find((a) => a.frameId === opts.frameId)
      if (!found) throw new Error('no assessment')
      return found
    })
    const result = await analyzeBundle(bundle, {
      detector: DETECTOR,
      analyzeFrame,
      decodeFrameImage,
    })
    expect(result.disposition).toBe('QUALITY_READY')
    expect(result.eligibleFrameIds).toHaveLength(6)
  })
})
