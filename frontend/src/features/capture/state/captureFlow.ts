/**
 * Frontend capture-flow state machine (M2 §20-22 + M3 §60).
 *
 * Deliberately separate from the M1 backend SessionState — this is the UI capture lifecycle
 * (CaptureFlowState). Loose boolean flags are not used; impossible transitions throw.
 *
 * M3 adds: CAPTURING -> ANALYZING -> PREVIEW | QUALITY_RETRY | ERROR; QUALITY_RETRY -> STREAMING.
 *
 * Valid transitions:
 *   IDLE --START_CAMERA--> REQUESTING_PERMISSION
 *   REQUESTING_PERMISSION --PERMISSION_OK--> STREAMING | --PERMISSION_ERROR--> ERROR
 *   STREAMING --SWITCH_CAMERA--> SWITCHING_CAMERA --SWITCH_OK|SWITCH_ERROR--> STREAMING
 *   STREAMING --CAPTURE--> CAPTURING --BURST_COMPLETE--> ANALYZING
 *   ANALYZING --ANALYSIS_READY--> PREVIEW | --ANALYSIS_RETRY--> QUALITY_RETRY | --ANALYSIS_ERROR--> ERROR
 *   PREVIEW --RETAKE--> REQUESTING_PERMISSION | --CONFIRM--> CONFIRMED
 *   QUALITY_RETRY --RETRY_RETAKE--> STREAMING
 *   ERROR --RESUME_STREAM--> STREAMING | --START_CAMERA--> REQUESTING_PERMISSION
 *   any --RESET--> IDLE
 *   SWITCHING_CAMERA --SWITCH_LOST--> ERROR (camera could not be recovered)
 *   REQUESTING_PERMISSION|STREAMING|SWITCHING_CAMERA|CAPTURING|ANALYZING|QUALITY_RETRY
 *       --INTERRUPTED--> ERROR
 */

import type { FlowError } from '../hooks/flowError'

export type CaptureFlowPhase =
  | 'idle'
  | 'requestingPermission'
  | 'streaming'
  | 'switchingCamera'
  | 'capturing'
  | 'analyzing'
  | 'qualityRetry'
  | 'preview'
  | 'confirmed'
  | 'error'

export interface CaptureFlowState {
  phase: CaptureFlowPhase
  error: FlowError | null
}

export type CaptureFlowAction =
  | { type: 'START_CAMERA' }
  | { type: 'PERMISSION_OK' }
  | { type: 'PERMISSION_ERROR'; error: FlowError }
  | { type: 'SWITCH_CAMERA' }
  | { type: 'SWITCH_OK' }
  | { type: 'SWITCH_ERROR'; error: FlowError }
  | { type: 'SWITCH_LOST'; error: FlowError }
  | { type: 'CAPTURE' }
  | { type: 'BURST_COMPLETE' }
  | { type: 'ANALYSIS_READY' }
  | { type: 'ANALYSIS_RETRY' }
  | { type: 'ANALYSIS_ERROR'; error: FlowError }
  | { type: 'RETRY_RETAKE' }
  | { type: 'RETAKE' }
  | { type: 'CONFIRM' }
  | { type: 'RESUME_STREAM' }
  | { type: 'RESET' }
  | { type: 'INTERRUPTED'; error: FlowError }

export const initialCaptureFlowState: CaptureFlowState = { phase: 'idle', error: null }

const ALLOWED_FROM: Record<CaptureFlowAction['type'], readonly CaptureFlowPhase[]> = {
  START_CAMERA: ['idle', 'error'],
  PERMISSION_OK: ['requestingPermission'],
  PERMISSION_ERROR: ['requestingPermission'],
  SWITCH_CAMERA: ['streaming'],
  SWITCH_OK: ['switchingCamera'],
  SWITCH_ERROR: ['switchingCamera'],
  SWITCH_LOST: ['switchingCamera'],
  CAPTURE: ['streaming'],
  BURST_COMPLETE: ['capturing'],
  ANALYSIS_READY: ['analyzing'],
  ANALYSIS_RETRY: ['analyzing'],
  ANALYSIS_ERROR: ['capturing', 'analyzing'],
  RETRY_RETAKE: ['qualityRetry'],
  RETAKE: ['preview'],
  CONFIRM: ['preview'],
  RESUME_STREAM: ['error'],
  RESET: [
    'idle',
    'requestingPermission',
    'streaming',
    'switchingCamera',
    'capturing',
    'analyzing',
    'qualityRetry',
    'preview',
    'confirmed',
    'error',
  ],
  INTERRUPTED: [
    'requestingPermission',
    'streaming',
    'switchingCamera',
    'capturing',
    'analyzing',
    'qualityRetry',
  ],
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
    case 'SWITCH_CAMERA':
      return { phase: 'switchingCamera', error: null }
    case 'PERMISSION_OK':
    case 'SWITCH_OK':
      return { phase: 'streaming', error: null }
    case 'PERMISSION_ERROR':
    case 'SWITCH_LOST':
    case 'ANALYSIS_ERROR':
    case 'INTERRUPTED':
      return { phase: 'error', error: action.error }
    case 'SWITCH_ERROR':
      // On switch failure the previous camera was recovered (M2 §17 / M3 §76).
      return { phase: 'streaming', error: null }
    case 'CAPTURE':
      return { phase: 'capturing', error: null }
    case 'BURST_COMPLETE':
      return { phase: 'analyzing', error: null }
    case 'ANALYSIS_READY':
      return { phase: 'preview', error: null }
    case 'ANALYSIS_RETRY':
      return { phase: 'qualityRetry', error: null }
    case 'RETRY_RETAKE':
      return { phase: 'streaming', error: null }
    case 'CONFIRM':
      return { phase: 'confirmed', error: null }
    case 'RESUME_STREAM':
      return { phase: 'streaming', error: null }
    case 'RESET':
      return { phase: 'idle', error: null }
  }
  return state
}
