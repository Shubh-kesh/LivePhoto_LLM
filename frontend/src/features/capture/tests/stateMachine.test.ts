/**
 * Capture-flow state machine tests (M2 §20-22 + M3 §60, §97). Valid transitions proceed;
 * impossible transitions throw, which is the double-click/race guard.
 */

import { describe, expect, it } from 'vitest'

import { CameraError } from '../media/mediaErrors'
import { QualityError } from '../quality/errors'
import {
  captureFlowReducer,
  initialCaptureFlowState,
  type CaptureFlowAction,
  type CaptureFlowState,
} from '../state/captureFlow'

const cameraErr = new CameraError('CAMERA_INTERRUPTED')
const qualityErr = new QualityError('QUALITY_ANALYSIS_ERROR')

function run(actions: CaptureFlowAction[]): CaptureFlowState {
  return actions.reduce(captureFlowReducer, initialCaptureFlowState)
}

const happyPath: CaptureFlowAction[] = [
  { type: 'START_CAMERA' },
  { type: 'PERMISSION_OK' },
  { type: 'CAPTURE' },
  { type: 'BURST_COMPLETE' },
  { type: 'ANALYSIS_READY' },
  { type: 'CONFIRM' },
]

describe('capture flow state machine', () => {
  it('runs the happy path to confirmed', () => {
    expect(run(happyPath).phase).toBe('confirmed')
  })

  it('supports a preview retake through the full cycle', () => {
    const state = run([
      ...happyPath.slice(0, 5),
      { type: 'RETAKE' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_COMPLETE' },
      { type: 'ANALYSIS_READY' },
      { type: 'CONFIRM' },
    ])
    expect(state.phase).toBe('confirmed')
  })

  it('tracks permission errors to the error phase', () => {
    const state = run([{ type: 'START_CAMERA' }, { type: 'PERMISSION_ERROR', error: cameraErr }])
    expect(state.phase).toBe('error')
    expect(state.error).toBe(cameraErr)
  })

  it('supports the quality-retry cycle back to streaming', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_COMPLETE' },
      { type: 'ANALYSIS_RETRY' },
      { type: 'RETRY_RETAKE' },
    ])
    expect(state.phase).toBe('streaming')
  })

  it('routes analysis errors to the error phase', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_COMPLETE' },
      { type: 'ANALYSIS_ERROR', error: qualityErr },
    ])
    expect(state.phase).toBe('error')
    expect(state.error).toBe(qualityErr)
  })

  it('keeps streaming after a recovered switch failure', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'SWITCH_CAMERA' },
      { type: 'SWITCH_ERROR', error: cameraErr },
    ])
    expect(state.phase).toBe('streaming')
  })

  it('routes a lost camera to the error phase', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'SWITCH_CAMERA' },
      { type: 'SWITCH_LOST', error: cameraErr },
    ])
    expect(state.phase).toBe('error')
  })

  it('returns to streaming after an error via RESUME_STREAM', () => {
    const state = run([
      ...happyPath.slice(0, 4),
      { type: 'ANALYSIS_ERROR', error: qualityErr },
      { type: 'RESUME_STREAM' },
    ])
    expect(state.phase).toBe('streaming')
  })

  it('supports interruption from active camera/analysis phases', () => {
    const interruptedFromStreaming = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'INTERRUPTED', error: cameraErr },
    ])
    const interruptedFromAnalyzing = run([
      ...happyPath.slice(0, 4),
      { type: 'INTERRUPTED', error: cameraErr },
    ])
    const interruptedFromRetry = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_COMPLETE' },
      { type: 'ANALYSIS_RETRY' },
      { type: 'INTERRUPTED', error: cameraErr },
    ])
    expect(interruptedFromStreaming.phase).toBe('error')
    expect(interruptedFromAnalyzing.phase).toBe('error')
    expect(interruptedFromRetry.phase).toBe('error')
  })

  it('reset returns to idle from any phase', () => {
    for (const phase of [
      'streaming',
      'capturing',
      'analyzing',
      'qualityRetry',
      'preview',
      'confirmed',
      'error',
    ] as const) {
      const state = captureFlowReducer({ phase, error: null }, { type: 'RESET' })
      expect(state.phase).toBe('idle')
    }
  })

  it('rejects impossible transitions', () => {
    const cases: Array<[CaptureFlowState, CaptureFlowAction]> = [
      [initialCaptureFlowState, { type: 'PERMISSION_OK' }],
      [initialCaptureFlowState, { type: 'CAPTURE' }],
      [{ phase: 'streaming', error: null }, { type: 'START_CAMERA' }],
      [{ phase: 'streaming', error: null }, { type: 'BURST_COMPLETE' }],
      [{ phase: 'capturing', error: null }, { type: 'ANALYSIS_READY' }],
      [{ phase: 'analyzing', error: null }, { type: 'CAPTURE' }],
      [{ phase: 'qualityRetry', error: null }, { type: 'CONFIRM' }],
      [{ phase: 'preview', error: null }, { type: 'BURST_COMPLETE' }],
    ]
    for (const [state, action] of cases) {
      expect(() => captureFlowReducer(state, action)).toThrow(/Invalid capture flow transition/)
    }
  })
})
