/**
 * Help bottom sheet (M5.5 §66-67).
 *
 * The sheet is a non-destructive overlay: the camera stream remains active underneath and the
 * guide keeps running; opening/closing help never stops or reacquires the stream, so privacy
 * semantics and lifecycle rules are unchanged. Documented in docs/CAPTURE_UX_DESIGN.md.
 */

import { useEffect } from 'react'
import { Button, IconHelp } from '../../../design-system'
import { captureCopy } from '../copy'

interface HelpSheetProps {
  onClose: () => void
}

export function HelpSheet({ onClose }: HelpSheetProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      className="lp-sheet"
      role="dialog"
      aria-modal="true"
      aria-labelledby="help-sheet-title"
      data-testid="help-sheet"
    >
      <div className="lp-sheet__backdrop" onClick={onClose} aria-hidden="true" />
      <div className="lp-sheet__panel">
        <div className="lp-sheet__header">
          <span className="lp-sheet__icon" aria-hidden="true">
            <IconHelp />
          </span>
          <h2 className="lp-sheet__title" id="help-sheet-title">
            {captureCopy.help.title}
          </h2>
        </div>
        <ul className="lp-sheet__list">
          {captureCopy.help.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <Button variant="primary" size="lg" className="lp-sheet__close" onClick={onClose}>
          {captureCopy.help.close}
        </Button>
      </div>
    </div>
  )
}
