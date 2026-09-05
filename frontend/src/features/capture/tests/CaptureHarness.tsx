/**
 * Test harness for the capture flow: renders a real <video> element wired to useCaptureFlow plus
 * buttons that drive the flow, and exposes phase/error/preview as data-testid spans. Used by
 * flow tests; the CapturePage integration test exercises the real components.
 */

import { useCaptureFlow } from '../hooks/useCaptureFlow'
import type { CaptureBundle } from '../types/capture'

export function CaptureHarness({
  onBundleReady,
}: {
  onBundleReady?: (bundle: CaptureBundle) => void
}) {
  const flow = useCaptureFlow({ onBundleReady })

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
      {button('confirm', flow.confirm)}
      {button('resume', flow.resumeStream)}
      {button('reset', flow.reset)}
      <span data-testid="phase">{flow.state}</span>
      <span data-testid="can-switch">{String(flow.canSwitchCamera)}</span>
      <span data-testid="retake-count">{flow.retakeCount}</span>
      <span data-testid="bundle-frames">{flow.bundle ? flow.bundle.frames.length : 'none'}</span>
      {flow.previewUrl && <img data-testid="preview-img" src={flow.previewUrl} alt="preview" />}
      {flow.error && <span data-testid="error-code">{flow.error.code}</span>}
      {flow.error && <span data-testid="error-message">{flow.error.safeMessage}</span>}
      {flow.transientMessage && <span data-testid="transient">{flow.transientMessage}</span>}
      {flow.captureProgress && <span data-testid="progress">{flow.captureProgress.captured}</span>}
    </div>
  )
}
