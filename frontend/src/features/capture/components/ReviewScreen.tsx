/** Review screen (M5.5 §37-39). Retake is secondary; Use photo is the primary CTA.
 *
 * A generic optional `diagnostics` slot renders below the Review actions (inside the Review
 * content). This keeps optional experiment/diagnostic UI inside the same flow instead of after a
 * full-viewport sibling (M5.6 correction). ReviewScreen never imports VLM components directly.
 */

import type { ReactNode } from 'react'

import { Button, ProgressSteps, ScreenLayout } from '../../../design-system'
import { captureCopy } from '../copy'

interface ReviewScreenProps {
  previewUrl: string
  onRetake: () => void
  onUsePhoto: () => void
  diagnostics?: ReactNode
}

export function ReviewScreen({ previewUrl, onRetake, onUsePhoto, diagnostics }: ReviewScreenProps) {
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
      {diagnostics}
    </ScreenLayout>
  )
}
