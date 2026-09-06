/**
 * Camera capture screen (M5.5 §16-28, §81-84).
 *
 * Mobile-first, camera-dominant. The <video> is a single stable DOM node, kept mounted (hidden)
 * across permission/analyzing/quality-retry phases so the attached stream survives transitions
 * (M2 §12, M3 §60). Preview mirroring is presentation-only (front mirrored, rear not); captured
 * pixels are never cropped or mirrored. The face guide is a CSS overlay only — it never crops the
 * frame, preserving full-frame environmental context for future spoof analysis. Guide states are
 * neutral / needs_attention / ready only — never liveness states.
 */

import type { RefObject } from 'react'

import { IconBack, IconCheck, IconHelp, IconSwitchCamera } from '../../../design-system'
import type { LiveGuidance } from '../quality/guidance/guidance'
import type { FaceDetectorProviderState } from '../quality/face/FaceDetectorProvider'
import type { CaptureProgress } from '../hooks/useCaptureFlow'
import { captureCopy } from '../copy'

type GuideVisualState = 'neutral' | 'needs_attention' | 'ready'

interface CameraScreenProps {
  videoRef: RefObject<HTMLVideoElement | null>
  isFrontCamera: boolean
  canSwitchCamera: boolean
  isCapturing: boolean
  isSwitching: boolean
  captureProgress: CaptureProgress | null
  transientMessage: string | null
  guidance?: LiveGuidance | null
  detectorStatus?: FaceDetectorProviderState | null
  /** Keep the video mounted (invisible) while permission is pending / analyzing / retry. */
  hidden?: boolean
  onSwitchCamera: () => void
  onCapture: () => void
  onBack: () => void
  onHelp: () => void
}

function visualStateFor(guideState: LiveGuidance['guideState']): GuideVisualState {
  if (guideState === 'ready') return 'ready'
  if (guideState === 'guidance') return 'needs_attention'
  return 'neutral'
}

export function CameraScreen({
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
  onBack,
  onHelp,
}: CameraScreenProps) {
  const busy = isCapturing || isSwitching
  const guideState = visualStateFor(guidance?.guideState ?? 'neutral')
  const isReady = guidance?.guideState === 'ready'

  return (
    <div className={hidden ? 'camera-screen camera-screen--hidden' : 'camera-screen'}>
      {/* Stable video node — always mounted while the camera session may be alive. */}
      <video
        ref={videoRef}
        className={
          isFrontCamera
            ? 'camera-screen__video camera-screen__video--mirror'
            : 'camera-screen__video'
        }
        autoPlay
        muted
        playsInline
        data-testid="camera-video"
      />

      {!hidden && (
        <>
          <div className="camera-screen__topbar">
            <button
              type="button"
              className="camera-screen__top-action"
              onClick={onBack}
              aria-label={captureCopy.camera.back}
            >
              <IconBack />
            </button>
            <span className="camera-screen__step" aria-hidden="true">
              {captureCopy.progress.capture}
            </span>
            <button
              type="button"
              className="camera-screen__top-action"
              onClick={onHelp}
              aria-label={captureCopy.camera.help}
            >
              <IconHelp />
            </button>
          </div>

          <div className="camera-screen__stage">
            <FaceGuide state={guideState} />
            <div className="camera-screen__guidance" role="status">
              <p className="camera-screen__guidance-message" key={guidance?.message ?? 'none'}>
                {isReady && <IconCheck width={18} height={18} />}
                {guidance?.message ?? captureCopy.camera.positionFace}
              </p>
              {detectorStatus === 'LOADING' && (
                <p className="camera-screen__sub-status">{captureCopy.camera.detectorLoading}</p>
              )}
              {detectorStatus === 'ERROR' && (
                <p className="camera-screen__sub-status">
                  {captureCopy.camera.detectorUnavailable}
                </p>
              )}
              {transientMessage && <p className="camera-screen__transient">{transientMessage}</p>}
            </div>
            {isCapturing && (
              <div className="camera-screen__hold" role="status">
                <span className="camera-screen__hold-dots" aria-hidden="true" />
                {captureCopy.camera.holdStill}
                {captureProgress && (
                  <span className="camera-screen__sr-only">
                    {captureProgress.captured}/{captureProgress.target}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="camera-screen__controls">
            {canSwitchCamera && (
              <button
                type="button"
                className="camera-screen__switch"
                onClick={onSwitchCamera}
                disabled={busy}
                aria-label={captureCopy.camera.switchCamera}
                title={captureCopy.camera.switchCamera}
              >
                <IconSwitchCamera />
              </button>
            )}
            <button
              type="button"
              className="camera-screen__shutter"
              onClick={onCapture}
              disabled={busy}
              aria-label={captureCopy.camera.capture}
            >
              <span className="camera-screen__shutter-inner" aria-hidden="true" />
              <span className="camera-screen__shutter-label">{captureCopy.camera.capture}</span>
            </button>
            {canSwitchCamera ? (
              <span className="camera-screen__switch-slot" aria-hidden="true" />
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}

function FaceGuide({ state }: { state: GuideVisualState }) {
  return (
    <div className="camera-screen__guide" aria-hidden="true">
      <div className={`camera-screen__oval camera-screen__oval--${state}`} />
    </div>
  )
}
