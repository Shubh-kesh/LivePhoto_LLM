/**
 * Capture data contracts (M2 §31-33, §80, §96).
 *
 * CaptureFrame / CaptureBundle are local in-memory application objects. They are NOT an API
 * payload, are NOT serialized to local storage, and must remain available to the next pipeline
 * stage (M3) until explicitly disposed.
 *
 * `captureId` is a local random identifier (crypto.randomUUID where available). It is distinct
 * from `transaction_id`, `session_id` and `decision_id` and must not be confused with them.
 */

import type { SafeTrackSettings } from './camera'

export interface CaptureFrame {
  id: string
  sequence: number
  capturedAtMs: number
  blob: Blob
  mimeType: string
  width: number
  height: number
  byteSize: number

  mediaTime?: number
  presentedFrames?: number
}

export interface CaptureBundle {
  captureId: string
  createdAt: string
  captureConfigVersion: string

  camera: SafeTrackSettings

  frames: CaptureFrame[]
  representativeFrameId: string
}

export type FrameScheduler = 'rvf' | 'rAF'

/** Local, non-persisted capture diagnostics (M2 §82). Development display only. */
export interface CaptureDiagnostics {
  cameraStartMs: number | null
  burstDurationMs: number | null
  totalFlowMs: number | null
  frameCount: number
  totalBytes: number
  width: number | null
  height: number | null
  frameRate: number | null
  facingMode: string | null
  scheduler: FrameScheduler | null
}
