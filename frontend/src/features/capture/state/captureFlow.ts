/**
 * Frontend capture-flow state machine (M2 §20-22, §52-53).
 *
 * Deliberately separate from the M1 backend SessionState — this is the UI capture lifecycle
 * (CaptureFlowState), not the bank session lifecycle. Loose boolean flags (isLoading/hasCamera/
 * isCapturing/hasPhoto) are not used; impossible transitions are prevented by the reducer, which
 * throws on an invalid action for the current phase.
 *
 * Valid transitions (M2 §22):
 *   IDLE --START_CAMERA--> REQUESTING_PERMISSION
 *   REQUESTING_PERMISSION --PERMISSION_OK--> STREAMING | --PERMISSION_ERROR--> ERROR
 *   STREAMING --SWITCH_CAMERA--> SWITCHING_CAMERA --SWITCH_OK|SWITCH_ERROR--> STREAMING
 *   STREAMING --CAPTURE--> CAPTURING --BURST_OK--> PREVIEW | --BURST_ERROR--> ERROR
 *   PREVIEW --RETAKE--> REQUESTING_PERMISSION | --CONFIRM--> CONFIRMED
 *   ERROR --RESUME_STREAM--> STREAMING (camera still active) | --START_CAMERA--> REQUESTING_PERMISSION
 *   any --RESET--> IDLE
 *   REQUESTING_PERMISSION|STREAMING|SWITCHING_CAMERA|CAPTURING --INTERRUPTED--> ERROR
 */

import type { CameraError } from '../media/mediaErrors'

export type CaptureFlowPhase =
  | 'idle'
  | 'requestingPermission'
  | 'streaming'
  | 'switchingCamera'
  | 'capturing'
  | 'preview'
  | 'confirmed'
  | 'error'

export interface CaptureFlowState {
  phase: CaptureFlowPhase
  error: CameraError | null
}

export type CaptureFlowAction =
  | { type: 'START_CAMERA' }
  | { type: 'PERMISSION_OK' }
  | { type: 'PERMISSION_ERROR'; error: CameraError }
  | { type: 'SWITCH_CAMERA' }
  | { type: 'SWITCH_OK' }
  | { type: 'SWITCH_ERROR'; error: CameraError }
  | { type: 'CAPTURE' }
  | { type: 'BURST_OK' }
  | { type: 'BURST_ERROR'; error: CameraError }
  | { type: 'RETAKE' }
  | { type: 'CONFIRM' }
  | { type: 'RESUME_STREAM' }
  | { type: 'RESET' }
  | { type: 'INTERRUPTED'; error: CameraError }

export const initialCaptureFlowState: CaptureFlowState = { phase: 'idle', error: null }

const ALLOWED_FROM: Record<CaptureFlowAction['type'], readonly CaptureFlowPhase[]> = {
  START_CAMERA: ['idle', 'error'],
  PERMISSION_OK: ['requestingPermission'],
  PERMISSION_ERROR: ['requestingPermission'],
  SWITCH_CAMERA: ['streaming'],
  SWITCH_OK: ['switchingCamera'],
  SWITCH_ERROR: ['switchingCamera'],
  CAPTURE: ['streaming'],
  BURST_OK: ['capturing'],
  BURST_ERROR: ['capturing'],
  RETAKE: ['preview'],
  CONFIRM: ['preview'],
  RESUME_STREAM: ['error'],
  RESET: [
    'idle',
    'requestingPermission',
    'streaming',
    'switchingCamera',
    'capturing',
    'preview',
    'confirmed',
    'error',
  ],
  INTERRUPTED: ['requestingPermission', 'streaming', 'switchingCamera', 'capturing'],
}

export function captureFlowReducer(
  state: CaptureFlowState,
  action: CaptureFlowAction,
): CaptureFlowState {
  const allowed = ALLOWED_FROM[action.type]
  if (!allowed.includes(state.phase)) {
    throw new Error(`Invalid capture flow transition: ${state.phase} -> ${action.type}`)
  }

  switch (action.type) {
    case 'START_CAMERA':
    case 'RETAKE':
      return { phase: 'requestingPermission', error: null }
    case 'PERMISSION_OK':
      return { phase: 'streaming', error: null }
    case 'PERMISSION_ERROR':
      return { phase: 'error', error: action.error }
    case 'SWITCH_CAMERA':
      return { phase: 'switchingCamera', error: null }
    case 'SWITCH_OK':
    case 'SWITCH_ERROR':
      // On switch failure the current camera remains active (M2 §17).
      return { phase: 'streaming', error: null }
    case 'CAPTURE':
      return { phase: 'capturing', error: null }
    case 'BURST_OK':
      return { phase: 'preview', error: null }
    case 'BURST_ERROR':
      return { phase: 'error', error: action.error }
    case 'CONFIRM':
      return { phase: 'confirmed', error: null }
    case 'RESUME_STREAM':
      return { phase: 'streaming', error: null }
    case 'RESET':
      return { phase: 'idle', error: null }
    case 'INTERRUPTED':
      return { phase: 'error', error: action.error }
  }
}
