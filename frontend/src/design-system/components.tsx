/** Small reusable design-system components (M5.5 §42). */

import type { ButtonHTMLAttributes, ReactNode } from 'react'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'md' | 'lg'
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`lp-btn lp-btn--${variant} lp-btn--${size} ${className}`.trim()}
      {...rest}
    />
  )
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  icon: ReactNode
}

export function IconButton({ label, icon, className = '', ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`lp-icon-btn ${className}`.trim()}
      {...rest}
    >
      {icon}
    </button>
  )
}

export type ProgressStep = 'prepare' | 'capture' | 'review'

const STEPS: ReadonlyArray<{ id: ProgressStep; label: string }> = [
  { id: 'prepare', label: 'Prepare' },
  { id: 'capture', label: 'Capture' },
  { id: 'review', label: 'Review' },
]

export function ProgressSteps({ active }: { active: ProgressStep }) {
  const activeIndex = STEPS.findIndex((step) => step.id === active)
  return (
    <ol className="lp-steps" aria-label="Progress">
      {STEPS.map((step, index) => (
        <li
          key={step.id}
          className={`lp-steps__item ${
            index === activeIndex ? 'lp-steps__item--active' : ''
          } ${index < activeIndex ? 'lp-steps__item--done' : ''}`}
          aria-current={index === activeIndex ? 'step' : undefined}
        >
          <span className="lp-steps__dot" aria-hidden="true" />
          <span className="lp-steps__label">{step.label}</span>
          {index < STEPS.length - 1 && <span className="lp-steps__divider" aria-hidden="true" />}
        </li>
      ))}
    </ol>
  )
}

export type StatusVariant = 'info' | 'warning' | 'danger' | 'success'

export function StatusMessage({
  variant = 'info',
  role = 'status',
  children,
}: {
  variant?: StatusVariant
  role?: 'status' | 'alert'
  children: ReactNode
}) {
  return (
    <div className={`lp-status lp-status--${variant}`} role={role}>
      {children}
    </div>
  )
}

export function ScreenLayout({ children }: { children: ReactNode }) {
  return (
    <div className="lp-screen">
      <div className="lp-screen__inner">{children}</div>
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`lp-card ${className}`.trim()}>{children}</div>
}

export function LoadingIndicator({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="lp-loading" role="status">
      <span className="lp-spinner" aria-hidden="true" />
      <span className="lp-loading__label">{label}</span>
    </div>
  )
}

export function BrandHeader({
  brandName = 'LivePhoto',
  logo,
}: {
  brandName?: string
  logo?: ReactNode
}) {
  return (
    <header className="lp-brand">
      {logo ?? (
        <span className="lp-brand__mark" aria-hidden="true">
          L
        </span>
      )}
      <span className="lp-brand__name">{brandName}</span>
    </header>
  )
}
