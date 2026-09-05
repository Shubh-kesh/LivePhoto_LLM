/**
 * frameAnalyzer tests (M3 §28-29, §93, §115). Uses a fake detector and an injected buildBuffer so
 * no canvas/ImageData or real model is needed.
 */

import { describe, expect, it } from 'vitest'

import { analyzeFrame } from '../engine/frameAnalyzer'
import { FakeFaceDetector } from '../../tests/qualityFakes'
import type { AnalysisBuffer } from '../metrics/types'
import { checkerboardGray } from './helpers'
import type { QualityConfig } from '../config/qualityConfig'
import { qualityConfig } from '../config/qualityConfig'

function goodBuffer(): AnalysisBuffer {
  return checkerboardGray(64, 48, 0.31, 0.7, 2)
}

const SOURCE = { width: 640, height: 480 } as unknown as CanvasImageSource

async function analyzeWith(detector: FakeFaceDetector, config?: QualityConfig) {
  return analyzeFrame({
    source: SOURCE,
    detector,
    frameId: 'f1',
    sequence: 0,
    config,
    buildBuffer: () => goodBuffer(),
    now: () => 0,
  })
}

describe('analyzeFrame', () => {
  it('marks a centered face frame as ELIGIBLE with no reasons', async () => {
    const detector = new FakeFaceDetector()
    detector.mode = 'good'
    const assessment = await analyzeWith(detector)
    expect(assessment.disposition).toBe('ELIGIBLE')
    expect(assessment.reasonCodes).toEqual([])
    expect(assessment.face.count).toBe(1)
    expect(assessment.face.detectionConfidence).toBeGreaterThan(0.9)
    expect(assessment.face.coverageRatio).toBeGreaterThan(0)
    expect(assessment.scores.overallQuality).toBeGreaterThan(0.8)
    expect(assessment.metricResults.length).toBeGreaterThan(0)
    expect(assessment.analysisTimeMs).toBe(0)
  })

  it('NO_FACE -> INELIGIBLE with NO_FACE reason', async () => {
    const detector = new FakeFaceDetector()
    detector.mode = 'noface'
    const assessment = await analyzeWith(detector)
    expect(assessment.disposition).toBe('INELIGIBLE')
    expect(assessment.reasonCodes).toContain('NO_FACE')
  })

  it('MULTIPLE_FACES -> INELIGIBLE', async () => {
    const detector = new FakeFaceDetector()
    detector.mode = 'multiple'
    const assessment = await analyzeWith(detector)
    expect(assessment.disposition).toBe('INELIGIBLE')
    expect(assessment.reasonCodes).toContain('MULTIPLE_FACES')
    expect(assessment.face.count).toBe(2)
  })

  it('FACE_TOO_SMALL -> INELIGIBLE', async () => {
    const detector = new FakeFaceDetector()
    detector.mode = 'toosmall'
    const assessment = await analyzeWith(detector)
    expect(assessment.disposition).toBe('INELIGIBLE')
    expect(assessment.reasonCodes).toContain('FACE_TOO_SMALL')
  })

  it('FACE_OFF_CENTER is soft (still ELIGIBLE)', async () => {
    const offCenterDetector = {
      info: { name: 'fake', version: '1', modelVersion: '1' },
      state: 'READY' as const,
      initialize: async () => undefined,
      dispose: () => undefined,
      detect: async () => ({
        detections: [
          {
            confidence: 0.95,
            boundingBox: { x: 0, y: 20, width: 200, height: 200 },
            normalizedBoundingBox: { x: 0 / 640, y: 20 / 480, width: 200 / 640, height: 200 / 480 },
          },
        ],
        imageWidth: 640,
        imageHeight: 480,
      }),
    }
    const assessment = await analyzeFrame({
      source: SOURCE,
      detector: offCenterDetector,
      frameId: 'f1',
      sequence: 0,
      buildBuffer: () => goodBuffer(),
      now: () => 0,
    })
    expect(assessment.reasonCodes).toContain('FACE_OFF_CENTER')
    expect(assessment.disposition).toBe('ELIGIBLE')
  })

  it('detector failure is FACE_ANALYSIS_UNAVAILABLE, never NO_FACE', async () => {
    const detector = new FakeFaceDetector()
    detector.failDetect = true
    const assessment = await analyzeWith(detector)
    expect(assessment.reasonCodes).toContain('FACE_ANALYSIS_UNAVAILABLE')
    expect(assessment.reasonCodes).not.toContain('NO_FACE')
    expect(assessment.disposition).toBe('ANALYSIS_UNAVAILABLE')
  })

  it('pixel-analysis failure is QUALITY_ANALYSIS_ERROR, never an image-quality reason', async () => {
    const detector = new FakeFaceDetector()
    detector.mode = 'good'
    const assessment = await analyzeFrame({
      source: SOURCE,
      detector,
      frameId: 'f1',
      sequence: 0,
      buildBuffer: () => {
        throw new Error('canvas unavailable')
      },
      now: () => 0,
    })
    expect(assessment.reasonCodes).toContain('QUALITY_ANALYSIS_ERROR')
    expect(assessment.reasonCodes).not.toContain('BLURRED')
    expect(assessment.disposition).toBe('ANALYSIS_UNAVAILABLE')
  })

  it('records raw metric values per observability contract', async () => {
    const detector = new FakeFaceDetector()
    detector.mode = 'good'
    const assessment = await analyzeWith(detector)
    const sharpness = assessment.metricResults.find((m) => m.metric === 'sharpness')
    expect(sharpness).toBeDefined()
    expect(sharpness?.rawValue).toBeGreaterThan(0)
    expect(sharpness?.threshold).toBe(qualityConfig.sharpness.blurThreshold)
    expect(['ACCEPTABLE', 'UNACCEPTABLE']).toContain(sharpness?.result)
  })
})
