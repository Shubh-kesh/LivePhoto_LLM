/** Review screen (M5.5 §37-39). Retake is secondary; Use photo is the primary CTA. */

import { Button, ProgressSteps, ScreenLayout } from '../../../design-system'
import { captureCopy } from '../copy'

interface ReviewScreenProps {
  previewUrl: string
  onRetake: () => void
  onUsePhoto: () => void
}

export function ReviewScreen({ previewUrl, onRetake, onUsePhoto }: ReviewScreenProps) {
  return (
    <ScreenLayout>
      <ProgressSteps active="review" />
      <h1 className="lp-title">{captureCopy.review.title}</h1>
      <p className="lp-subtitle">{captureCopy.review.body}</p>
      <img
        className="lp-review__image"
        src={previewUrl}
        alt="Your captured photo preview"
        data-testid="review-image"
      />
      <div className="lp-review__actions">
        <Button variant="secondary" size="lg" onClick={onRetake}>
          {captureCopy.review.retake}
        </Button>
        <Button variant="primary" size="lg" onClick={onUsePhoto}>
          {captureCopy.review.usePhoto}
        </Button>
      </div>
    </ScreenLayout>
  )
}
