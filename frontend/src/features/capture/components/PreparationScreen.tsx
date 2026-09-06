/** Preparation / welcome screen (M5.5 §4, §9, §11-12, §60). Shown on every fresh visit/reload. */

import { BrandHeader, Button, IconCheck, ProgressSteps, ScreenLayout } from '../../../design-system'
import { captureCopy } from '../copy'
import { InstructionAnimation } from './InstructionAnimation'

interface PreparationScreenProps {
  onContinue: () => void
}

const INSTRUCTIONS: ReadonlyArray<{ key: string; text: string }> = [
  { key: 'mask', text: captureCopy.prepare.mask },
  { key: 'spectacles', text: captureCopy.prepare.spectacles },
  { key: 'faceVisible', text: captureCopy.prepare.faceVisible },
  { key: 'lighting', text: captureCopy.prepare.lighting },
]

export function PreparationScreen({ onContinue }: PreparationScreenProps) {
  return (
    <ScreenLayout>
      <BrandHeader brandName={captureCopy.brand.name} />
      <ProgressSteps active="prepare" />
      <h1 className="lp-title">{captureCopy.prepare.title}</h1>
      <p className="lp-subtitle">{captureCopy.prepare.beforeWeBegin}</p>
      <InstructionAnimation />
      <ul className="lp-prep-list" data-testid="preparation-instructions">
        {INSTRUCTIONS.map(({ key, text }) => (
          <li key={key} className="lp-prep-list__item">
            <span className="lp-prep-list__check" aria-hidden="true">
              <IconCheck width={16} height={16} />
            </span>
            {text}
          </li>
        ))}
      </ul>
      <p className="lp-hint lp-prep-footer">{captureCopy.prepare.footer}</p>
      <Button variant="primary" size="lg" className="lp-prep-cta" onClick={onContinue}>
        {captureCopy.prepare.continue}
      </Button>
    </ScreenLayout>
  )
}
