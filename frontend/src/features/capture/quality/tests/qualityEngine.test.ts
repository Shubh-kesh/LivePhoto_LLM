/**
 * Quality-engine tests: normalization, component scores, reason derivation, hard/soft rules.
 */

import { describe, expect, it } from 'vitest'

import { qualityConfig } from '../config/qualityConfig'
import type { FaceMetrics } from '../types/face'
import type { ExposureMetrics } from '../types/quality'
import {
  computeComponentScores,
  deriveReasonCodes,
  isHardBlocker,
  normalizeContrast,
  normalizeExposure,
  normalizeFace,
  normalizeSharpness,
} from '../engine/qualityEngine'
import { faceCenterOffset, faceCoverageRatio, normalizeBox } from '../face/faceGeometry'

const GOOD_EXPOSURE: ExposureMetrics = {
  meanLuminance: 0.5,
  darkPixelRatio: 0.05,
  brightPixelRatio: 0.05,
}

function centeredFace(coverage: number, distance = 0, confidence = 0.95): FaceMetrics {
  return {
    count: 1,
    detectionConfidence: confidence,
    coverageRatio: coverage,
    centerOffset: { dx: distance, dy: distance, distance },
  }
}

const GOOD_DIMS = { width: 640, height: 480 }

describe('normalization', () => {
  it('is bounded 0..1 and deterministic', () => {
    const exposure = normalizeExposure(GOOD_EXPOSURE, qualityConfig)
    expect(exposure).toBeGreaterThanOrEqual(0)
    expect(exposure).toBeLessThanOrEqual(1)
    expect(normalizeExposure(GOOD_EXPOSURE, qualityConfig)).toBe(exposure)
    expect(normalizeContrast(0.2, qualityConfig)).toBe(1)
    expect(normalizeSharpness(300, qualityConfig)).toBe(1)
    expect(normalizeSharpness(50, qualityConfig)).toBeCloseTo(0.5, 3)
  })

  it('penalizes underexposure via dark-pixel ratio', () => {
    const score = normalizeExposure(
      { meanLuminance: 0.5, darkPixelRatio: 1, brightPixelRatio: 0 },
      qualityConfig,
    )
    expect(score).toBe(0)
  })

  it('face score is zero when no/multiple faces', () => {
    expect(normalizeFace({ count: 0 }, qualityConfig)).toBe(0)
    expect(normalizeFace({ count: 2 }, qualityConfig)).toBe(0)
  })

  it('face score reflects coverage and centering', () => {
    expect(normalizeFace(centeredFace(0.3), qualityConfig)).toBeCloseTo(1, 3)
    expect(normalizeFace(centeredFace(0.01), qualityConfig)).toBeLessThan(1)
    expect(normalizeFace(centeredFace(0.3, 0.5), qualityConfig)).toBeLessThan(1)
  })
})

describe('overall quality score', () => {
  it('is the minimum of applicable component scores (weakest dimension)', () => {
    const scores = computeComponentScores(GOOD_EXPOSURE, 0.2, 300, centeredFace(0.3), qualityConfig)
    const expected = Math.min(scores.exposure, scores.contrast, scores.sharpness, scores.face ?? 1)
    expect(scores.overallQuality).toBeCloseTo(expected, 6)
  })

  it('drops to zero when a hard dimension fails', () => {
    const scores = computeComponentScores(
      { meanLuminance: 0.05, darkPixelRatio: 1, brightPixelRatio: 0 },
      0.2,
      300,
      centeredFace(0.3),
      qualityConfig,
    )
    expect(scores.overallQuality).toBe(0)
  })
})

describe('reason derivation', () => {
  it('NO_FACE', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      { count: 0 },
      qualityConfig,
    )
    expect(reasons).toContain('NO_FACE')
  })

  it('MULTIPLE_FACES', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      { count: 2 },
      qualityConfig,
    )
    expect(reasons).toContain('MULTIPLE_FACES')
  })

  it('FACE_TOO_SMALL / FACE_TOO_LARGE', () => {
    const tooSmall = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      centeredFace(0.01),
      qualityConfig,
    )
    const tooLarge = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      centeredFace(0.9),
      qualityConfig,
    )
    expect(tooSmall).toContain('FACE_TOO_SMALL')
    expect(tooLarge).toContain('FACE_TOO_LARGE')
  })

  it('FACE_OFF_CENTER is a soft warning', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      centeredFace(0.3, 0.5),
      qualityConfig,
    )
    expect(reasons).toContain('FACE_OFF_CENTER')
    expect(isHardBlocker('FACE_OFF_CENTER')).toBe(false)
  })

  it('BLURRED when sharpness is below threshold', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      10,
      centeredFace(0.3),
      qualityConfig,
    )
    expect(reasons).toContain('BLURRED')
  })

  it('UNDEREXPOSED / OVEREXPOSED', () => {
    const dark = deriveReasonCodes(
      GOOD_DIMS,
      { meanLuminance: 0.05, darkPixelRatio: 1, brightPixelRatio: 0 },
      0.2,
      300,
      centeredFace(0.3),
      qualityConfig,
    )
    const bright = deriveReasonCodes(
      GOOD_DIMS,
      { meanLuminance: 0.95, darkPixelRatio: 0, brightPixelRatio: 1 },
      0.2,
      300,
      centeredFace(0.3),
      qualityConfig,
    )
    expect(dark).toContain('UNDEREXPOSED')
    expect(bright).toContain('OVEREXPOSED')
  })

  it('LOW_CONTRAST', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.01,
      300,
      centeredFace(0.3),
      qualityConfig,
    )
    expect(reasons).toContain('LOW_CONTRAST')
  })

  it('RESOLUTION_TOO_LOW', () => {
    const reasons = deriveReasonCodes(
      { width: 100, height: 80 },
      GOOD_EXPOSURE,
      0.2,
      300,
      centeredFace(0.3),
      qualityConfig,
    )
    expect(reasons).toContain('RESOLUTION_TOO_LOW')
  })

  it('no reasons for a good frame', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      centeredFace(0.3),
      qualityConfig,
    )
    expect(reasons).toEqual([])
  })
})

describe('face geometry', () => {
  it('computes coverage and center offset from normalized boxes', () => {
    const box = normalizeBox({ x: 100, y: 80, width: 200, height: 200 }, 640, 480)
    expect(faceCoverageRatio(box)).toBeCloseTo((200 / 640) * (200 / 480), 6)
    const offset = faceCenterOffset(box)
    expect(offset.dx).toBeCloseTo((100 + 100) / 640 - 0.5, 6)
    expect(offset.distance).toBeGreaterThan(0)
  })
})
