/**
 * Capture page (M2 §1, §45, §55-59 + M3 §60-68). Wires the capture flow into a responsive,
 * accessible UI with live quality guidance, quality analysis and quality-retry states.
 * No liveness language is ever shown.
 */

import { useCallback, useState } from 'react'

import { CameraErrorState } from './components/CameraErrorState'
import { CameraIntroduction } from './components/CameraIntroduction'
import { CameraViewport } from './components/CameraViewport'
import { CaptureDiagnostics } from './components/CaptureDiagnostics'
import { CapturePreview } from './components/CapturePreview'
import { QualityChecking } from './components/QualityChecking'
import { QualityRetryScreen } from './components/QualityRetryScreen'
import { useCaptureFlow, type UseCaptureFlowResult } from './hooks/useCaptureFlow'
import type { CaptureBundle } from './types/capture'
import type { FaceDetectorProvider } from './quality/face/FaceDetectorProvider'
import type { BundleQualityAssessment } from './quality/types/quality'
import './capture.css'

export function CapturePage({
  faceDetector,
  analyzeBundle,
}: {
  faceDetector?: FaceDetectorProvider
  analyzeBundle?: (bundle: CaptureBundle) => Promise<BundleQualityAssessment>
}) {
  const [confirmedBundle, setConfirmedBundle] = useState<CaptureBundle | null>(null)
  const onBundleReady = useCallback((bundle: CaptureBundle) => {
    setConfirmedBundle(bundle)
  }, [])

  const flow = useCaptureFlow({ onBundleReady, faceDetector, analyzeBundle })
  const isFrontCamera = flow.cameraSettings.facingMode !== 'environment'
  // Keep the single stable <video> mounted for every phase where the camera session may be alive
  // so the attached stream survives phase transitions (M2 §12, M3 §60).
  const activeCameraPhases = [
    'requestingPermission',
    'streaming',
    'switchingCamera',
    'capturing',
    'analyzing',
    'qualityRetry',
  ] as const
  const isActiveCameraPhase = activeCameraPhases.includes(
    flow.state as (typeof activeCameraPhases)[number],
  )

  return (
    <main className="capture-page">
      <h1>LivePhoto</h1>

      {(flow.state === 'idle' || flow.state === 'requestingPermission') && (
        <CameraIntroduction
          onStart={() => void flow.startCamera()}
          pending={flow.state === 'requestingPermission'}
        />
      )}

      {isActiveCameraPhase && (
        <CameraViewport
          videoRef={flow.videoRef}
          isFrontCamera={isFrontCamera}
          canSwitchCamera={flow.canSwitchCamera}
          isCapturing={flow.state === 'capturing'}
          isSwitching={flow.state === 'switchingCamera'}
          captureProgress={flow.captureProgress}
          transientMessage={flow.transientMessage}
          guidance={flow.liveGuidance}
          detectorStatus={flow.detectorState}
          hidden={flow.state === 'requestingPermission'}
          onSwitchCamera={() => void flow.switchCamera()}
          onCapture={() => void flow.capture()}
        />
      )}

      {flow.state === 'analyzing' && <QualityChecking />}

      {flow.state === 'qualityRetry' && (
        <QualityRetryScreen
          guidance={flow.retryGuidance}
          onRetake={() => void flow.retryRetake()}
          onReset={flow.reset}
        />
      )}

      {flow.state === 'preview' && flow.previewUrl && (
        <CapturePreview
          previewUrl={flow.previewUrl}
          onRetake={() => void flow.retake()}
          onConfirm={flow.confirm}
        />
      )}

      {flow.state === 'confirmed' && (
        <section className="capture-confirmed" aria-labelledby="capture-confirmed-heading">
          <h2 id="capture-confirmed-heading">Photo captured successfully.</h2>
          {import.meta.env.DEV && confirmedBundle && (
            <p className="capture-confirmed__meta">
              Bundle ready for the next pipeline stage (frames: {confirmedBundle.frames.length}).
            </p>
          )}
          <button type="button" className="camera-control" onClick={flow.reset}>
            Start over
          </button>
        </section>
      )}

      {flow.state === 'error' && flow.error && (
        <CameraErrorState
          error={flow.error}
          canRetryStream={flow.canRetryStream}
          onRetryStream={flow.resumeStream}
          onRestart={() => void flow.startCamera()}
          onReset={flow.reset}
        />
      )}

      <CaptureDiagnostics
        diagnostics={flow.diagnostics}
        quality={{ bundle: flow.qualityAssessment }}
      />
    </main>
  )
}

export type { UseCaptureFlowResult }
