/**
 * Closed-eye frame gate tests (M5.7 §16-18, §27, §31, §33). Uses the real analyzeFrame with a fake
 * detector + fake eye-state evaluator; no canvas/model required.
 */

import { describe, expect, it } from 'vitest'

import { analyzeFrame } from '../engine/frameAnalyzer'
import { FakeEyeStateEvaluator, FakeFaceDetector } from '../../tests/qualityFakes'
import type { AnalysisBuffer } from '../metrics/types'
import { checkerboardGray } from './helpers'

function goodBuffer(): AnalysisBuffer {
  return checkerboardGray(64, 48, 0.31, 0.7, 2)
}

const SOURCE = { width: 640, height: 480 } as unknown as CanvasImageSource

async function analyzeWith(eyeMode: FakeEyeStateEvaluator['mode']) {
  const eye = new FakeEyeStateEvaluator()
  eye.mode = eyeMode
  return analyzeFrame({
    source: SOURCE,
    detector: new FakeFaceDetector(),
    eyeEvaluator: eye,
    frameId: 'f1',
    sequence: 0,
    buildBuffer: () => goodBuffer(),
    now: () => 0,
  })
}

describe('analyzeFrame eye gate', () => {
  it('both eyes open -> ELIGIBLE with no eye reason', async () => {
    const assessment = await analyzeWith('open')
    expect(assessment.disposition).toBe('ELIGIBLE')
    expect(assessment.reasonCodes).not.toContain('EYES_CLOSED')
    expect(assessment.eyeState?.eyesOpen).toBe(true)
  })

  it('left eye closed -> EYES_CLOSED and INELIGIBLE', async () => {
    const assessment = await analyzeWith('left_closed')
    expect(assessment.reasonCodes).toContain('EYES_CLOSED')
    expect(assessment.disposition).toBe('INELIGIBLE')
    expect(assessment.eyeState?.eyesOpen).toBe(false)
  })

  it('right eye closed -> EYES_CLOSED and INELIGIBLE', async () => {
    const assessment = await analyzeWith('right_closed')
    expect(assessment.reasonCodes).toContain('EYES_CLOSED')
    expect(assessment.disposition).toBe('INELIGIBLE')
  })

  it('both eyes closed -> EYES_CLOSED and INELIGIBLE', async () => {
    const assessment = await analyzeWith('closed')
    expect(assessment.reasonCodes).toContain('EYES_CLOSED')
    expect(assessment.disposition).toBe('INELIGIBLE')
  })

  it('unreliable eye state -> EYE_STATE_UNKNOWN and INELIGIBLE (never safe by default)', async () => {
    const assessment = await analyzeWith('unknown')
    expect(assessment.reasonCodes).toContain('EYE_STATE_UNKNOWN')
    expect(assessment.disposition).toBe('INELIGIBLE')
    expect(assessment.eyeState?.evaluated).toBe(false)
  })
})
