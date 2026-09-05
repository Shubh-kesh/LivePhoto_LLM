/**
 * Camera-facing types (M2 §19).
 *
 * SafeTrackSettings intentionally excludes identifiers such as `deviceId` and `groupId`: they
 * must not be included in ordinary telemetry or logs (M2 §19, §95).
 */

export type FacingMode = 'user' | 'environment'

export interface SafeTrackSettings {
  width?: number
  height?: number
  frameRate?: number
  aspectRatio?: number
  facingMode?: string
}

export interface CameraSession {
  stream: MediaStream
  track: MediaStreamTrack
  settings: SafeTrackSettings
  stop(): void
}

/** requestVideoFrameCallback metadata (feature-detected; not required by M2). */
export interface VideoFrameCallbackMetadata {
  presentationTime: number
  expectedDisplayTime: number
  width: number
  height: number
  mediaTime: number
  presentedFrames: number
  processingDuration?: number
}

export type VideoFrameRequestCallback = (now: number, metadata: VideoFrameCallbackMetadata) => void

export interface HTMLVideoElementWithRVFC extends HTMLVideoElement {
  requestVideoFrameCallback(callback: VideoFrameRequestCallback): number
  cancelVideoFrameCallback(handle: number): void
}
