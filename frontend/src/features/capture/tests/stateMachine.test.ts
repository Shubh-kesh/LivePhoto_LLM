/**
 * Capture-flow state machine tests (M2 §20-22). Valid transitions proceed; impossible
 * transitions throw, which is the double-click/race guard.
 */

import { describe, expect, it } from 'vitest'

import { CameraError } from '../media/mediaErrors'
import {
  captureFlowReducer,
  initialCaptureFlowState,
  type CaptureFlowAction,
  type CaptureFlowState,
} from '../state/captureFlow'

const err = new CameraError('CAMERA_INTERRUPTED')

function run(actions: CaptureFlowAction[]): CaptureFlowState {
  return actions.reduce(captureFlowReducer, initialCaptureFlowState)
}

describe('capture flow state machine', () => {
  it('runs the happy path to confirmed', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_OK' },
      { type: 'CONFIRM' },
    ])
    expect(state.phase).toBe('confirmed')
  })

  it('supports retake through the full cycle', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_OK' },
      { type: 'RETAKE' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_OK' },
      { type: 'CONFIRM' },
    ])
    expect(state.phase).toBe('confirmed')
  })

  it('tracks permission errors to the error phase', () => {
    const state = run([{ type: 'START_CAMERA' }, { type: 'PERMISSION_ERROR', error: err }])
    expect(state.phase).toBe('error')
    expect(state.error).toBe(err)
  })

  it('returns to streaming after a burst error via RESUME_STREAM', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'BURST_ERROR', error: err },
      { type: 'RESUME_STREAM' },
    ])
    expect(state.phase).toBe('streaming')
  })

  it('keeps streaming after a switch failure', () => {
    const state = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'SWITCH_CAMERA' },
      { type: 'SWITCH_ERROR', error: err },
    ])
    expect(state.phase).toBe('streaming')
  })

  it('supports interruption from active camera phases', () => {
    const interruptedFromStreaming = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'INTERRUPTED', error: err },
    ])
    const interruptedFromCapturing = run([
      { type: 'START_CAMERA' },
      { type: 'PERMISSION_OK' },
      { type: 'CAPTURE' },
      { type: 'INTERRUPTED', error: err },
    ])
    expect(interruptedFromStreaming.phase).toBe('error')
    expect(interruptedFromCapturing.phase).toBe('error')
  })

  it('reset returns to idle from any phase', () => {
    for (const phase of ['streaming', 'capturing', 'preview', 'confirmed', 'error'] as const) {
      let state: CaptureFlowState = { phase, error: null }
      state = captureFlowReducer(state, { type: 'RESET' })
      expect(state.phase).toBe('idle')
    }
  })

  it('rejects impossible transitions', () => {
    const cases: Array<[CaptureFlowState, CaptureFlowAction]> = [
      [initialCaptureFlowState, { type: 'PERMISSION_OK' }],
      [initialCaptureFlowState, { type: 'CAPTURE' }],
      [{ phase: 'streaming', error: null }, { type: 'START_CAMERA' }],
      [{ phase: 'streaming', error: null }, { type: 'BURST_OK' }],
      [{ phase: 'preview', error: null }, { type: 'CAPTURE' }],
      [{ phase: 'capturing', error: null }, { type: 'CONFIRM' }],
    ]
    for (const [state, action] of cases) {
      expect(() => captureFlowReducer(state, action)).toThrow(/Invalid capture flow transition/)
    }
  })
})
