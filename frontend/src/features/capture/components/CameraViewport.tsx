/**
 * Camera viewport (M2 §12-13, §17, §40-41, §55-59 + M3 §64-68).
 *
 * The <video> remains a single stable DOM node (hidden only while permission is requested) so the
 * attached stream survives phase transitions. The visual face guide reflects live quality state
 * (neutral/guidance/ready) but never uses color alone; the guidance text is announced via
 * role="status". The guide is presentation only — captured pixels are never cropped to it, and
 * front-camera mirroring is a CSS preview transform only.
 */

import type { RefObject } from 'react'

import type { LiveGuidance } from '../quality/guidance/guidance'
import type { FaceDetectorProviderState } from '../quality/face/FaceDetectorProvider'
import type { CaptureProgress } from '../hooks/useCaptureFlow'

interface CameraViewportProps {
  videoRef: RefObject<HTMLVideoElement | null>
  isFrontCamera: boolean
  canSwitchCamera: boolean
  isCapturing: boolean
  isSwitching: boolean
  captureProgress: CaptureProgress | null
  transientMessage: string | null
  guidance?: LiveGuidance | null
  detectorStatus?: FaceDetectorProviderState | null
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
  guidance,
  detectorStatus,
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
        <CameraGuide state={guidance?.guideState ?? 'neutral'} />
        {isCapturing && <CaptureProgress progress={captureProgress} />}
      </div>

      {guidance && (
        <p className="capture-guidance-message" role="status">
          {guidance.message}
        </p>
      )}

      {detectorStatus === 'LOADING' && (
        <p className="capture-detector-status" role="status">
          Preparing quality check…
        </p>
      )}
      {detectorStatus === 'ERROR' && (
        <p className="capture-detector-status" role="status">
          Quality check is unavailable.
        </p>
      )}

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

function CameraGuide({ state }: { state: 'neutral' | 'guidance' | 'ready' }) {
  return (
    <div className="camera-guide" aria-hidden="true">
      <div className={`camera-guide__oval camera-guide__oval--${state}`} />
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
