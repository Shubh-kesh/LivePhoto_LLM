/**
 * Guidance tests (M3 §62-65, §81-82, §98): message priority, stabilization, retry guidance.
 */

import { describe, expect, it } from 'vitest'

import type { FrameQualityAssessment } from '../types/quality'
import {
  buildLiveGuidance,
  categoryFromAssessment,
  guidanceFromReasonCodes,
  guidanceMessage,
  GuidanceStabilizer,
} from '../guidance/guidance'

function assessment(reasonCodes: string[], overallQuality = 0.3): FrameQualityAssessment {
  return {
    frameId: 'f',
    sequence: 0,
    configVersion: 'quality-v1',
    dimensions: { width: 640, height: 480, pixelCount: 640 * 480 },
    face: { count: reasonCodes.includes('NO_FACE') ? 0 : 1 },
    exposure: { meanLuminance: 0.5, darkPixelRatio: 0.05, brightPixelRatio: 0.05 },
    contrast: { rawValue: 0.2 },
    sharpness: { rawValue: 300 },
    scores: {
      face: 1,
      exposure: 1,
      contrast: 1,
      sharpness: 1,
      overallQuality,
    },
    metricResults: [],
    reasonCodes: reasonCodes as FrameQualityAssessment['reasonCodes'],
    disposition: 'ELIGIBLE',
    analysisTimeMs: 1,
  }
}

describe('guidance priority', () => {
  it('NO_FACE overrides blur', () => {
    const category = categoryFromAssessment(assessment(['NO_FACE', 'BLURRED']))
    expect(category).toBe('NO_FACE')
  })

  it('MULTIPLE_FACES overrides centering', () => {
    const category = categoryFromAssessment(assessment(['MULTIPLE_FACES', 'FACE_OFF_CENTER']))
    expect(category).toBe('MULTIPLE_FACES')
  })

  it('severe exposure overrides a mild centering warning', () => {
    const category = categoryFromAssessment(assessment(['UNDEREXPOSED', 'FACE_OFF_CENTER']))
    expect(category).toBe('EXPOSURE')
  })

  it('blur outranks centering', () => {
    const category = categoryFromAssessment(assessment(['BLURRED', 'FACE_OFF_CENTER']))
    expect(category).toBe('BLUR')
  })

  it('READY only when quality is high and no blockers', () => {
    expect(categoryFromAssessment(assessment([], 0.95))).toBe('READY')
    expect(categoryFromAssessment(assessment([], 0.3))).toBe('NEUTRAL')
  })
})

describe('guidance messages', () => {
  it('are capture-quality statements only', () => {
    expect(guidanceMessage('NO_FACE')).toContain('face')
    expect(guidanceMessage('TOO_FAR')).toBe('Move closer to the camera.')
    expect(guidanceMessage('BLUR')).toBe('Hold still.')
    expect(guidanceMessage('READY')).toBe('Ready to capture.')
    const all = Object.values(guidanceMessage)
    expect(all.join(' ')).not.toMatch(/live|verified|spoof|genuine|authenticated/i)
  })

  it('buildLiveGuidance maps to a guide visual state', () => {
    expect(buildLiveGuidance('READY').guideState).toBe('ready')
    expect(buildLiveGuidance('NEUTRAL').guideState).toBe('neutral')
    expect(buildLiveGuidance('TOO_FAR').guideState).toBe('guidance')
  })
})

describe('retry guidance priority', () => {
  it('maps aggregated reasons to one useful action', () => {
    expect(guidanceFromReasonCodes(['NO_FACE'])).toBe('NO_FACE')
    expect(guidanceFromReasonCodes(['UNDEREXPOSED'])).toBe('EXPOSURE')
    expect(guidanceFromReasonCodes(['BLURRED', 'FACE_OFF_CENTER'])).toBe('BLUR')
    expect(guidanceFromReasonCodes([])).toBe('NEUTRAL')
  })
})

describe('GuidanceStabilizer', () => {
  it('requires the same category for N consecutive analyses', () => {
    const stabilizer = new GuidanceStabilizer(2)
    expect(stabilizer.update('TOO_FAR')).toBeNull()
    expect(stabilizer.update('TOO_FAR')).toBe('TOO_FAR')
    expect(stabilizer.update('TOO_FAR')).toBe('TOO_FAR')
  })

  it('resets on category change', () => {
    const stabilizer = new GuidanceStabilizer(2)
    expect(stabilizer.update('TOO_FAR')).toBeNull()
    expect(stabilizer.update('BLUR')).toBeNull()
    expect(stabilizer.update('BLUR')).toBe('BLUR')
  })

  it('supports reset()', () => {
    const stabilizer = new GuidanceStabilizer(2)
    stabilizer.update('READY')
    stabilizer.update('READY')
    stabilizer.reset()
    expect(stabilizer.update('READY')).toBeNull()
  })
})
