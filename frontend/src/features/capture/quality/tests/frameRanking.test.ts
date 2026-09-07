/**
 * Frame-ranking tests (M3 §96). Selection must be deterministic and quality-driven.
 */

import { describe, expect, it } from 'vitest'

import { selectEligibleFrame } from '../engine/frameRanking'
import type { FrameQualityAssessment } from '../types/quality'

function assessment(
  sequence: number,
  overrides: Partial<FrameQualityAssessment> & {
    overallQuality: number
    confidence?: number
    centerDistance?: number
  },
): FrameQualityAssessment {
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
      overallQuality: overrides.overallQuality,
    },
    metricResults: [],
    reasonCodes: [],
    disposition: overrides.disposition ?? 'ELIGIBLE',
    analysisTimeMs: 1,
  }
}

describe('selectEligibleFrame', () => {
  it('returns null when no frames are eligible', () => {
    const result = selectEligibleFrame([
      assessment(0, { overallQuality: 0, disposition: 'INELIGIBLE' }),
    ])
    expect(result.selectedId).toBeNull()
  })

  it('selects the only eligible frame', () => {
    const result = selectEligibleFrame([
      assessment(0, { overallQuality: 0.4, disposition: 'INELIGIBLE' }),
      assessment(1, { overallQuality: 0.9 }),
      assessment(2, { overallQuality: 0.5, disposition: 'INELIGIBLE' }),
    ])
    expect(result.selectedId).toBe('frame-1')
  })

  it('picks the highest overall quality among eligible frames', () => {
    const result = selectEligibleFrame([
      assessment(0, { overallQuality: 0.6 }),
      assessment(1, { overallQuality: 0.97 }),
      assessment(2, { overallQuality: 0.8 }),
    ])
    expect(result.selectedId).toBe('frame-1')
  })

  it('breaks quality ties by detection confidence', () => {
    const result = selectEligibleFrame([
      assessment(0, { overallQuality: 0.9, confidence: 0.6 }),
      assessment(1, { overallQuality: 0.9, confidence: 0.98 }),
    ])
    expect(result.selectedId).toBe('frame-1')
  })

  it('breaks confidence ties by center proximity', () => {
    const result = selectEligibleFrame([
      assessment(0, { overallQuality: 0.9, confidence: 0.9, centerDistance: 0.4 }),
      assessment(1, { overallQuality: 0.9, confidence: 0.9, centerDistance: 0.05 }),
    ])
    expect(result.selectedId).toBe('frame-1')
  })

  it('final tie-break is the frame closest to the temporal center (earliest wins)', () => {
    const result = selectEligibleFrame(
      [0, 1, 2, 3, 4, 5, 6, 7].map((i) => assessment(i, { overallQuality: 0.9 })),
    )
    expect(result.selectedId).toBe('frame-3')
    expect(result.selectionScore).toBe(0.9)
    expect(result.algorithmVersion).toBe('frame-ranking-v2')
  })

  it('is deterministic across calls', () => {
    const frames = [0, 1, 2, 3, 4].map((i) => assessment(i, { overallQuality: 0.9 }))
    expect(selectEligibleFrame(frames).selectedId).toBe(selectEligibleFrame(frames).selectedId)
  })
})
