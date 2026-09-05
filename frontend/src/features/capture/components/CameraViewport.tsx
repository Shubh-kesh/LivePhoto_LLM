/**
 * Camera viewport (M2 §12-13, §17, §40-41, §55-59).
 *
 * The <video> is rendered here and remains the SAME DOM node from permission-request through
 * capture (the whole viewport is only visually hidden during permission), so the attached stream
 * (srcObject) survives phase transitions. The visual face guide is presentation only; captured
 * pixels are never cropped to it. Front-camera mirroring is a CSS preview transform only —
 * captured pixels keep the camera's natural orientation (M2 §13).
 */

import type { RefObject } from 'react'

import type { CaptureProgress } from '../hooks/useCaptureFlow'

interface CameraViewportProps {
  videoRef: RefObject<HTMLVideoElement | null>
  isFrontCamera: boolean
  canSwitchCamera: boolean
  isCapturing: boolean
  isSwitching: boolean
  captureProgress: CaptureProgress | null
  transientMessage: string | null
  /** Visually hide (keep mounted) while permission is requested so the stream can attach. */
  hidden?: boolean
  onSwitchCamera: () => void
  onCapture: () => void
}

export function CameraViewport({
  videoRef,
  isFrontCamera,
  canSwitchCamera,
  isCapturing,
  isSwitching,
  captureProgress,
  transientMessage,
  hidden = false,
  onSwitchCamera,
  onCapture,
}: CameraViewportProps) {
  const busy = isCapturing || isSwitching
  const rootClass = hidden ? 'camera-viewport camera-viewport--hidden' : 'camera-viewport'

  return (
    <div className={rootClass}>
      <div className="camera-stage">
        <video
          ref={videoRef}
          className={isFrontCamera ? 'camera-video camera-video--mirror' : 'camera-video'}
          autoPlay
          muted
          playsInline
          data-testid="camera-video"
        />
        <CameraGuide />
        {isCapturing && <CaptureProgress progress={captureProgress} />}
      </div>

      {transientMessage && (
        <p className="capture-transient-message" role="status">
          {transientMessage}
        </p>
      )}

      <div className="camera-controls">
        {canSwitchCamera && (
          <button
            type="button"
            className="camera-control"
            onClick={onSwitchCamera}
            disabled={busy}
            aria-label="Switch camera"
          >
            Switch camera
          </button>
        )}
        <button
          type="button"
          className="capture-button"
          onClick={onCapture}
          disabled={busy}
          aria-label="Capture photo"
        >
          Capture photo
        </button>
      </div>
    </div>
  )
}

function CameraGuide() {
  return (
    <div className="camera-guide" aria-hidden="true">
      <div className="camera-guide__oval" />
    </div>
  )
}

function CaptureProgress({ progress }: { progress: CaptureProgress | null }) {
  const value = progress ? `${progress.captured}/${progress.target}` : ''
  return (
    <div className="capture-progress" role="status">
      <p>Hold still…</p>
      {progress && <p>{value}</p>}
    </div>
  )
}
