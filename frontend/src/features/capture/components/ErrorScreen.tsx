/**
 * Camera / technical error screen (M5.5 §33-36, §78). Camera errors and quality-analysis failures
 * are kept visually and semantically separate. DOMException wording is never exposed.
 */

import {
  Button,
  IconWarning,
  ProgressSteps,
  ScreenLayout,
  StatusMessage,
} from '../../../design-system'
import type { FlowError } from '../hooks/flowError'
import { captureCopy, errorCopyFor } from '../copy'

interface ErrorScreenProps {
  error: FlowError
  onRetry: () => void
  onReset: () => void
}

export function ErrorScreen({ error, onRetry, onReset }: ErrorScreenProps) {
  const copy = errorCopyFor(error)
  return (
    <ScreenLayout>
      <ProgressSteps active="capture" />
      <div className="lp-error" data-testid="capture-error">
        <div className="lp-error__icon" aria-hidden="true">
          <IconWarning width={40} height={40} />
        </div>
        <h1 className="lp-title">{copy.title}</h1>
        <StatusMessage variant="danger" role="alert">
          {copy.body}
        </StatusMessage>
        <div className="lp-error__actions">
          <Button variant="primary" size="lg" onClick={onRetry}>
            {captureCopy.errors.tryAgain}
          </Button>
          <Button variant="ghost" onClick={onReset}>
            {captureCopy.errors.backToStart}
          </Button>
        </div>
      </div>
    </ScreenLayout>
  )
}
