/**
 * Burst eye-selection tests (M5.7 §28-29, §32-33, frame-ranking-v2).
 *
 * Closed-eye / unreliable-eye frames are INELIGIBLE and can never become the final selected frame;
 * a good open-eye frame is preferred even if a closed-eye frame had higher raw quality; if no
 * acceptable open-eye frame exists the burst retries. Applies to the primary face only.
 */

import { describe, expect, it } from 'vitest'

import { analyzeBundle } from '../engine/bundleAnalyzer'
import { selectEligibleFrame } from '../engine/frameRanking'
import type { CaptureBundle } from '../../types/capture'
import type { EyeStateEvidence, FaceMetrics } from '../types/face'
import type { FrameQualityAssessment, QualityReasonCode } from '../types/quality'

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

function eyeState(eyesOpen: boolean): EyeStateEvidence {
  return { evaluated: true, leftEyeOpen: eyesOpen, rightEyeOpen: eyesOpen, eyesOpen }
}

function face(confidence = 0.95, count = 1): FaceMetrics {
  return {
    count,
    detectionConfidence: confidence,
    coverageRatio: 0.3,
    centerOffset: { dx: 0, dy: 0, distance: 0 },
  }
}

function assessment(
  sequence: number,
  overrides: {
    eyesOpen?: boolean
    overallQuality?: number
    reasons?: QualityReasonCode[]
    confidence?: number
  } = {},
): FrameQualityAssessment {
  const eyesOpen = overrides.eyesOpen ?? true
  const reasons = overrides.reasons ?? []
  const eligible = reasons.length === 0
  return {
    frameId: `frame-${sequence}`,
    sequence,
    configVersion: 'quality-v1',
    dimensions: { width: 640, height: 480, pixelCount: 640 * 480 },
    face: face(overrides.confidence),
    eyeState: eyeState(eyesOpen),
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
    reasonCodes: reasons,
    disposition: eligible ? 'ELIGIBLE' : 'INELIGIBLE',
    analysisTimeMs: 1,
  }
}

describe('burst eye selection', () => {
  it('7 closed-eye frames + 1 open-eye frame -> selects the open-eye frame', () => {
    const assessments = [
      ...Array.from({ length: 7 }, (_, i) =>
        assessment(i, { eyesOpen: false, reasons: ['EYES_CLOSED'] }),
      ),
      assessment(7, { eyesOpen: true, overallQuality: 0.85 }),
    ]
    const selected = selectEligibleFrame(assessments)
    expect(selected.selectedId).toBe('frame-7')
    expect(selected.algorithmVersion).toBe('frame-ranking-v2')
  })

  it('open-eye frame with LOWER quality still wins over a closed-eye frame', () => {
    const assessments = [
      assessment(0, { eyesOpen: false, reasons: ['EYES_CLOSED'], overallQuality: 0.99 }),
      assessment(1, { eyesOpen: true, overallQuality: 0.6 }),
    ]
    const selected = selectEligibleFrame(assessments)
    expect(selected.selectedId).toBe('frame-1')
  })

  it('all frames closed -> no selection (retry with EYES_CLOSED)', () => {
    const assessments = Array.from({ length: 8 }, (_, i) =>
      assessment(i, { eyesOpen: false, reasons: ['EYES_CLOSED'] }),
    )
    const selected = selectEligibleFrame(assessments)
    expect(selected.selectedId).toBeNull()
    // Bundle-level retry surfaces EYES_CLOSED as the common reason.
    expect(aggregate(assessments)).toContain('EYES_CLOSED')
  })

  it('mixed blink sequence -> closed-eye frames are ignored', () => {
    const assessments = [
      assessment(0, { eyesOpen: false, reasons: ['EYES_CLOSED'], overallQuality: 0.9 }),
      assessment(1, { eyesOpen: true, overallQuality: 0.7 }),
      assessment(2, { eyesOpen: false, reasons: ['EYES_CLOSED'], overallQuality: 0.95 }),
      assessment(3, { eyesOpen: true, overallQuality: 0.88 }),
    ]
    const selected = selectEligibleFrame(assessments)
    expect(selected.selectedId).toBe('frame-3')
  })

  it('all frames with unreliable eye state -> retry (EYE_STATE_UNKNOWN)', () => {
    const assessments = Array.from({ length: 8 }, (_, i) =>
      assessment(i, { eyesOpen: false, reasons: ['EYE_STATE_UNKNOWN'] }),
    )
    expect(selectEligibleFrame(assessments).selectedId).toBeNull()
    expect(aggregate(assessments)).toContain('EYE_STATE_UNKNOWN')
  })
})

describe('bundle-level retry with all closed eyes', () => {
  it('analyzeBundle -> QUALITY_RETRY with EYES_CLOSED when every frame is closed', async () => {
    const bundle = makeBundle(3)
    const analyze = async () => assessment(0, { eyesOpen: false, reasons: ['EYES_CLOSED'] })
    const result = await analyzeBundle(bundle, {
      detector: { info: { name: 'fake', version: '1', modelVersion: 'v1' } } as never,
      analyzeFrame: analyze as never,
      decodeFrameImage: async (blob: Blob) => ({
        image: blob as unknown as CanvasImageSource,
        close: () => undefined,
      }),
      now: () => 0,
    })
    expect(result.disposition).toBe('QUALITY_RETRY')
    expect(result.reasonCodes).toContain('EYES_CLOSED')
    expect(result.selectedFrameId).toBeUndefined()
  })
})

function aggregate(assessments: FrameQualityAssessment[]): QualityReasonCode[] {
  const counts = new Map<QualityReasonCode, number>()
  for (const a of assessments) {
    for (const reason of a.reasonCodes) counts.set(reason, (counts.get(reason) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([reason]) => reason)
}
