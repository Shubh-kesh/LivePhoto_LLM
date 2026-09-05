/**
 * Capture page (M2 §1, §45, §55-59). Wires the capture flow into a responsive, accessible UI.
 * No liveness language is shown: the only completion statement is "Photo captured successfully."
 */

import { useCallback, useState } from 'react'

import { CameraErrorState } from './components/CameraErrorState'
import { CameraIntroduction } from './components/CameraIntroduction'
import { CameraViewport } from './components/CameraViewport'
import { CaptureDiagnostics } from './components/CaptureDiagnostics'
import { CapturePreview } from './components/CapturePreview'
import { useCaptureFlow, type UseCaptureFlowResult } from './hooks/useCaptureFlow'
import type { CaptureBundle } from './types/capture'
import './capture.css'

export function CapturePage() {
  const [confirmedBundle, setConfirmedBundle] = useState<CaptureBundle | null>(null)
  const onBundleReady = useCallback((bundle: CaptureBundle) => {
    setConfirmedBundle(bundle)
  }, [])

  const flow = useCaptureFlow({ onBundleReady })
  const isFrontCamera = flow.cameraSettings.facingMode !== 'environment'

  return (
    <main className="capture-page">
      <h1>LivePhoto</h1>

      {(flow.state === 'requestingPermission' ||
        flow.state === 'streaming' ||
        flow.state === 'switchingCamera' ||
        flow.state === 'capturing') && (
        <CameraViewport
          videoRef={flow.videoRef}
          isFrontCamera={isFrontCamera}
          canSwitchCamera={flow.canSwitchCamera}
          isCapturing={flow.state === 'capturing'}
          isSwitching={flow.state === 'switchingCamera'}
          captureProgress={flow.captureProgress}
          transientMessage={flow.transientMessage}
          hidden={flow.state === 'requestingPermission'}
          onSwitchCamera={() => void flow.switchCamera()}
          onCapture={() => void flow.capture()}
        />
      )}

      {(flow.state === 'idle' || flow.state === 'requestingPermission') && (
        <CameraIntroduction
          onStart={() => void flow.startCamera()}
          pending={flow.state === 'requestingPermission'}
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

      <CaptureDiagnostics diagnostics={flow.diagnostics} />
    </main>
  )
}

export type { UseCaptureFlowResult }
