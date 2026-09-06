/** Quality-analysis screen (M5.5 §29-30). Subtle progress only; no percentages or metrics. */

import { LoadingIndicator, ProgressSteps, ScreenLayout } from '../../../design-system'
import { captureCopy } from '../copy'

export function QualityCheckingScreen() {
  return (
    <ScreenLayout>
      <ProgressSteps active="capture" />
      <div className="lp-checking">
        <LoadingIndicator label={captureCopy.camera.checking} />
      </div>
    </ScreenLayout>
  )
}
