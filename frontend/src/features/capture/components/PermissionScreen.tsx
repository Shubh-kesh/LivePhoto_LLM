/** Camera permission explanation screen (M5.5 §13-15). Explains why before invoking getUserMedia. */

import {
  BrandHeader,
  Button,
  Card,
  IconBack,
  IconButton,
  IconCamera,
  ProgressSteps,
  ScreenLayout,
} from '../../../design-system'
import { captureCopy } from '../copy'

interface PermissionScreenProps {
  onOpenCamera: () => void
  onBack: () => void
}

export function PermissionScreen({ onOpenCamera, onBack }: PermissionScreenProps) {
  return (
    <ScreenLayout>
      <IconButton label={captureCopy.camera.back} icon={<IconBack />} onClick={onBack} />
      <BrandHeader brandName={captureCopy.brand.name} />
      <ProgressSteps active="capture" />
      <Card className="lp-permission">
        <div className="lp-permission__icon" aria-hidden="true">
          <IconCamera width={40} height={40} />
        </div>
        <h1 className="lp-title">{captureCopy.permission.title}</h1>
        <p className="lp-body">{captureCopy.permission.body}</p>
        <p className="lp-hint">{captureCopy.permission.microphone}</p>
        <Button variant="primary" size="lg" className="lp-permission__cta" onClick={onOpenCamera}>
          {captureCopy.permission.openCamera}
        </Button>
      </Card>
    </ScreenLayout>
  )
}
