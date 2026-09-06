/**
 * Quality-retry screen (M5.5 §31-32, §76-77). Reason codes are mapped to customer copy via
 * copy.ts; raw codes and technical diagnostics are never shown.
 */

import {
  Button,
  IconWarning,
  ProgressSteps,
  ScreenLayout,
  StatusMessage,
} from '../../../design-system'
import type { QualityReasonCode } from '../quality/types/quality'
import { captureCopy, retryCopyForReasonCodes } from '../copy'

interface QualityRetryScreenProps {
  reasonCodes: readonly QualityReasonCode[]
  onRetake: () => void
  onReset: () => void
}

export function QualityRetryScreen({ reasonCodes, onRetake, onReset }: QualityRetryScreenProps) {
  const copy = retryCopyForReasonCodes(reasonCodes)
  return (
    <ScreenLayout>
      <ProgressSteps active="capture" />
      <div className="lp-retry" data-testid="quality-retry">
        <div className="lp-retry__icon" aria-hidden="true">
          <IconWarning width={40} height={40} />
        </div>
        <h1 className="lp-title">{captureCopy.qualityRetry.title}</h1>
        <StatusMessage variant="warning" role="alert">
          <span>
            <strong>{copy.title}</strong> {copy.body}
          </span>
        </StatusMessage>
        <div className="lp-retry__actions">
          <Button variant="primary" size="lg" onClick={onRetake}>
            {captureCopy.qualityRetry.tryAgain}
          </Button>
          <Button variant="ghost" onClick={onReset}>
            {captureCopy.qualityRetry.backToStart}
          </Button>
        </div>
      </div>
    </ScreenLayout>
  )
}
