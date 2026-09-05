/**
 * Quality retry screen (M3 §62-63). Shows a single prioritized reason and retake/back actions.
 * Quality retry is capture-quality language only — never liveness language.
 */

import type { LiveGuidance } from '../quality/guidance/guidance'

interface QualityRetryScreenProps {
  guidance: LiveGuidance | null
  onRetake: () => void
  onReset: () => void
}

export function QualityRetryScreen({ guidance, onRetake, onReset }: QualityRetryScreenProps) {
  return (
    <section className="quality-retry" aria-labelledby="quality-retry-heading">
      <h2 id="quality-retry-heading">Photo needs to be retaken.</h2>
      <p className="quality-retry__reason" role="alert">
        {guidance?.message ?? 'Please try again.'}
      </p>
      <div className="quality-retry__actions">
        <button type="button" className="primary-action" onClick={onRetake}>
          Retake photo
        </button>
        <button type="button" className="camera-control" onClick={onReset}>
          Back to start
        </button>
      </div>
    </section>
  )
}
