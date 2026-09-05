/**
 * Camera error state (M2 §38-39, §58). Safe customer-facing messages only; raw browser messages
 * and device details are never shown.
 */

import type { CameraError } from '../media/mediaErrors'

interface CameraErrorStateProps {
  error: CameraError
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
  return (
    <section className="capture-error" aria-labelledby="capture-error-heading">
      <h2 id="capture-error-heading">We couldn't access your camera</h2>
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
