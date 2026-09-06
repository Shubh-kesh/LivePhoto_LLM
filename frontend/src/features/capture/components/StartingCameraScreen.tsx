/** Starting-camera screen shown while getUserMedia() is pending (M5.5 §62). */

import { BrandHeader, LoadingIndicator, ProgressSteps, ScreenLayout } from '../../../design-system'
import { captureCopy } from '../copy'

export function StartingCameraScreen() {
  return (
    <ScreenLayout>
      <BrandHeader brandName={captureCopy.brand.name} />
      <ProgressSteps active="capture" />
      <div className="lp-starting">
        <LoadingIndicator label={captureCopy.permission.starting} />
      </div>
    </ScreenLayout>
  )
}
