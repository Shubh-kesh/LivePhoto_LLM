/**
 * Face-participation heuristic tests (M5.7 §89-90).
 *
 * Two substantial frontal central faces -> MULTIPLE_FACES (quality retry). One central face plus a
 * small peripheral/background face/profile -> NOT automatically MULTIPLE_FACES (portrait matting
 * removes the background person).
 */

import { describe, expect, it } from 'vitest'

import { qualityConfig } from '../../config/qualityConfig'
import { deriveReasonCodes } from '../../engine/qualityEngine'
import type { FaceDetection } from '../../types/face'
import { participatingFaceCount, primaryFaceDetection } from '../faceParticipation'

function detection(x: number, y: number, w: number, h: number, confidence = 0.95): FaceDetection {
  return {
    confidence,
    boundingBox: {
      x: Math.round(x * 640),
      y: Math.round(y * 480),
      width: Math.round(w * 640),
      height: Math.round(h * 480),
    },
    normalizedBoundingBox: { x, y, width: w, height: h },
  }
}

describe('participatingFaceCount', () => {
  it('counts two substantial central faces as participating (M5.7 §28, §89)', () => {
    const detections = [detection(0.2, 0.2, 0.32, 0.32), detection(0.48, 0.25, 0.3, 0.3)]
    expect(participatingFaceCount(detections, qualityConfig)).toBe(2)
  })

  it('ignores a small peripheral background face (M5.7 §29-30, §90)', () => {
    const detections = [
      detection(0.34, 0.24, 0.32, 0.32), // primary, substantial, central
      detection(0.02, 0.02, 0.03, 0.03), // tiny, corner (background person)
    ]
    expect(participatingFaceCount(detections, qualityConfig)).toBe(1)
  })

  it('ignores a low-confidence face', () => {
    const detections = [detection(0.34, 0.24, 0.32, 0.32), detection(0.2, 0.2, 0.32, 0.32, 0.1)]
    expect(participatingFaceCount(detections, qualityConfig)).toBe(1)
  })

  it('primary detection is the largest participating face', () => {
    const primary = detection(0.34, 0.24, 0.32, 0.32)
    const detections = [detection(0.02, 0.02, 0.03, 0.03), primary]
    expect(primaryFaceDetection(detections, qualityConfig)?.normalizedBoundingBox).toEqual(
      primary.normalizedBoundingBox,
    )
  })
})

describe('deriveReasonCodes with participation', () => {
  const GOOD_DIMS = { width: 640, height: 480 }
  const GOOD_EXPOSURE = { meanLuminance: 0.5, darkPixelRatio: 0.05, brightPixelRatio: 0.05 }

  it('two participating faces -> MULTIPLE_FACES (M5.7 §89)', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      {
        count: 2,
        participatingCount: 2,
        coverageRatio: 0.3,
        centerOffset: { dx: 0, dy: 0, distance: 0 },
      },
      qualityConfig,
    )
    expect(reasons).toContain('MULTIPLE_FACES')
  })

  it('one central face + small peripheral face -> NOT MULTIPLE_FACES (M5.7 §90)', () => {
    const reasons = deriveReasonCodes(
      GOOD_DIMS,
      GOOD_EXPOSURE,
      0.2,
      300,
      {
        count: 2,
        participatingCount: 1,
        coverageRatio: 0.32,
        centerOffset: { dx: 0, dy: 0, distance: 0 },
      },
      qualityConfig,
    )
    expect(reasons).not.toContain('MULTIPLE_FACES')
    expect(reasons).not.toContain('NO_FACE')
  })
})
