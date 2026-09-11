/**
 * Primary face-box parameter extraction (geometry guidance for backend portrait processing).
 */

import { describe, expect, it } from 'vitest'

import { selectedFaceBoxParam } from '../faceBox'
import type { BundleQualityAssessment } from '../types/quality'

function assessmentWithFace(box: { x: number; y: number; width: number; height: number }) {
  return {
    captureId: 'c1',
    captureConfigVersion: 'v1',
    qualityConfigVersion: 'v1',
    frames: [
      {
        frameId: 'rep',
        sequence: 0,
        configVersion: 'v1',
        dimensions: { width: 100, height: 100, pixelCount: 10000 },
        face: { count: 1, normalizedBoundingBox: box },
        exposure: { meanLuminance: 0.5, darkPixelRatio: 0, brightPixelRatio: 0 },
        contrast: { rawValue: 0.5 },
        sharpness: { rawValue: 0.5 },
        scores: { exposure: 1, contrast: 1, sharpness: 1, overallQuality: 1 },
        metricResults: [],
        reasonCodes: [],
        disposition: 'ELIGIBLE',
        analysisTimeMs: 1,
      },
    ],
    eligibleFrameIds: ['rep'],
    selectionAlgorithmVersion: 'v1',
    disposition: 'QUALITY_READY',
    reasonCodes: [],
    totalAnalysisTimeMs: 1,
  } as unknown as BundleQualityAssessment
}

describe('selectedFaceBoxParam', () => {
  it('formats the selected frame primary face box as x,y,w,h', () => {
    const assessment = assessmentWithFace({ x: 0.3, y: 0.2, width: 0.4, height: 0.5 })
    expect(selectedFaceBoxParam(assessment, 'rep')).toBe('0.300000,0.200000,0.400000,0.500000')
  })

  it('returns undefined when assessment/frame/box is missing', () => {
    expect(selectedFaceBoxParam(null, 'rep')).toBeUndefined()
    expect(selectedFaceBoxParam(assessmentWithFace({ x: 0, y: 0, width: 0.1, height: 0.1 }), null)).toBeUndefined()
    expect(
      selectedFaceBoxParam(assessmentWithFace({ x: 0, y: 0, width: 0.1, height: 0.1 }), 'nope'),
    ).toBeUndefined()
  })

  it('rejects a degenerate box and clamps values into [0,1]', () => {
    expect(
      selectedFaceBoxParam(assessmentWithFace({ x: 0, y: 0, width: 0, height: 0 }), 'rep'),
    ).toBeUndefined()
    expect(
      selectedFaceBoxParam(
        assessmentWithFace({ x: -0.5, y: 1.5, width: 2, height: 0.5 }),
        'rep',
      ),
    ).toBe('0.000000,1.000000,1.000000,0.500000')
  })
})