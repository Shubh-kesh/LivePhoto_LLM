/**
 * Error state (M3 §113-115). Technical camera errors and quality-analysis failures are distinct:
 * the heading and message adapt to the error type. Safe customer-facing messages only.
 */

import type { FlowError } from '../hooks/flowError'
import { isQualityFlowError } from '../hooks/flowError'

interface CameraErrorStateProps {
  error: FlowError
  canRetryStream: boolean
  onRetryStream: () => void
  onRestart: () => void
  onReset: () => void
}

export function CameraErrorState({
  error,
  canRetryStream,
  onRetryStream,
  onRestart,
  onReset,
}: CameraErrorStateProps) {
  const heading = isQualityFlowError(error)
    ? "We couldn't check photo quality."
    : "We couldn't access your camera"
  return (
    <section className="capture-error" aria-labelledby="capture-error-heading">
      <h2 id="capture-error-heading">{heading}</h2>
      <p id="capture-error-message" role="alert">
        {error.safeMessage}
      </p>
      <div className="capture-error__actions">
        {canRetryStream ? (
          <button type="button" className="primary-action" onClick={onRetryStream}>
            Try again
          </button>
        ) : (
          <button type="button" className="primary-action" onClick={onRestart}>
            Try again
          </button>
        )}
        <button type="button" className="camera-control" onClick={onReset}>
          Back to start
        </button>
      </div>
    </section>
  )
}
