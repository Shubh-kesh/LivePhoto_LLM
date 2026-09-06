/** Final capture-success screen (M5.5 §40-41). Capture-success wording only — never verification. */

import { Button, IconCheck, ProgressSteps, ScreenLayout } from '../../../design-system'
import { captureCopy } from '../copy'

interface SuccessScreenProps {
  onStartOver: () => void
}

export function SuccessScreen({ onStartOver }: SuccessScreenProps) {
  return (
    <ScreenLayout>
      <ProgressSteps active="review" />
      <div className="lp-success" data-testid="capture-success">
        <div className="lp-success__icon" aria-hidden="true">
          <IconCheck width={36} height={36} />
        </div>
        <h1 className="lp-title">{captureCopy.success.title}</h1>
        <p className="lp-subtitle">{captureCopy.success.body}</p>
        <Button variant="ghost" onClick={onStartOver}>
          {captureCopy.success.startOver}
        </Button>
      </div>
    </ScreenLayout>
  )
}
