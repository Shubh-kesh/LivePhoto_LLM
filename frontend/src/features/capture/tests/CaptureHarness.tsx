/**
 * Test harness for the capture flow: renders a real <video> element wired to useCaptureFlow plus
 * buttons that drive the flow, and exposes phase/error/preview as data-testid spans. Tests inject
 * a deterministic face detector and bundle analyzer (M3 §100-102).
 */

import { useCaptureFlow } from '../hooks/useCaptureFlow'
import type { CaptureAttempt } from '../hooks/useCaptureFlow'
import type { FaceDetectorProvider } from '../quality/face/FaceDetectorProvider'
import type { BundleQualityAssessment } from '../quality/types/quality'
import type { CaptureBundle } from '../types/capture'

interface CaptureHarnessProps {
  faceDetector?: FaceDetectorProvider
  analyzeBundle?: (bundle: CaptureBundle) => Promise<BundleQualityAssessment>
  onBundleReady?: (bundle: CaptureBundle) => void
  onAttempt?: (attempt: CaptureAttempt) => void
}

export function CaptureHarness({
  faceDetector,
  analyzeBundle,
  onBundleReady,
  onAttempt,
}: CaptureHarnessProps) {
  const flow = useCaptureFlow({ onBundleReady, faceDetector, analyzeBundle, onAttempt })

  const button = (label: string, action: () => void) => (
    <button type="button" onClick={() => void action()}>
      {label}
    </button>
  )

  return (
    <div data-testid="capture-harness">
      <video ref={flow.videoRef} data-testid="harness-video" muted playsInline />
      {button('start', flow.startCamera)}
      {button('switch', flow.switchCamera)}
      {button('capture', flow.capture)}
      {button('retake', flow.retake)}
      {button('retry-retake', flow.retryRetake)}
      {button('confirm', flow.confirm)}
      {button('resume', flow.resumeStream)}
      {button('reset', flow.reset)}
      <span data-testid="phase">{flow.state}</span>
      <span data-testid="can-switch">{String(flow.canSwitchCamera)}</span>
      <span data-testid="retake-count">{flow.retakeCount}</span>
      <span data-testid="bundle-frames">{flow.bundle ? flow.bundle.frames.length : 'none'}</span>
      <span data-testid="detector-state">{flow.detectorState}</span>
      <span data-testid="quality-disposition">
        {flow.qualityAssessment ? flow.qualityAssessment.disposition : 'none'}
      </span>
      {flow.retryGuidance && <span data-testid="retry-guidance">{flow.retryGuidance.message}</span>}
      {flow.liveGuidance && <span data-testid="live-guidance">{flow.liveGuidance.message}</span>}
      {flow.previewUrl && <img data-testid="preview-img" src={flow.previewUrl} alt="preview" />}
      {flow.error && <span data-testid="error-code">{flow.error.code}</span>}
      {flow.error && <span data-testid="error-message">{flow.error.safeMessage}</span>}
      {flow.transientMessage && <span data-testid="transient">{flow.transientMessage}</span>}
      {flow.captureProgress && <span data-testid="progress">{flow.captureProgress.captured}</span>}
      <span data-testid="attempt-id">{flow.attemptId ?? 'none'}</span>
    </div>
  )
}
