/**
 * Design-system component tests (M5.5 §42-51, §57-58, §93).
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  BrandHeader,
  Button,
  IconButton,
  ProgressSteps,
  ScreenLayout,
  StatusMessage,
} from '../design-system'

describe('Button', () => {
  it('applies primary/secondary/ghost variants', () => {
    const { container } = render(
      <>
        <Button variant="primary">Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
      </>,
    )
    expect(container.querySelector('.lp-btn--primary')).not.toBeNull()
    expect(container.querySelector('.lp-btn--secondary')).not.toBeNull()
    expect(container.querySelector('.lp-btn--ghost')).not.toBeNull()
  })

  it('is keyboard accessible and clickable', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Go</Button>)
    const button = screen.getByRole('button', { name: 'Go' })
    button.click()
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})

describe('IconButton', () => {
  it('exposes a screen-reader label', () => {
    render(<IconButton label="Help" icon={<span>?</span>} />)
    expect(screen.getByRole('button', { name: 'Help' })).toBeInTheDocument()
  })
})

describe('ProgressSteps', () => {
  it('shows Prepare/Capture/Review and marks the active step', () => {
    const { container } = render(<ProgressSteps active="capture" />)
    expect(screen.getByLabelText('Progress')).toBeInTheDocument()
    expect(screen.getByText('Prepare')).toBeInTheDocument()
    expect(screen.getByText('Capture')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()
    const items = container.querySelectorAll('.lp-steps__item--active')
    expect(items).toHaveLength(1)
    expect(items[0]).toHaveTextContent('Capture')
  })

  it('never shows a complete state before review', () => {
    render(<ProgressSteps active="review" />)
    expect(screen.queryByText('Review complete')).not.toBeInTheDocument()
  })
})

describe('StatusMessage', () => {
  it('announces with role=status by default and role=alert when requested', () => {
    const { rerender } = render(<StatusMessage>Info</StatusMessage>)
    expect(screen.getByRole('status')).toHaveTextContent('Info')
    rerender(<StatusMessage role="alert">Alert</StatusMessage>)
    expect(screen.getByRole('alert')).toHaveTextContent('Alert')
  })
})

describe('BrandHeader', () => {
  it('defaults to LivePhoto and accepts a future brand name/logo', () => {
    const { rerender } = render(<BrandHeader />)
    expect(screen.getByText('LivePhoto')).toBeInTheDocument()
    rerender(<BrandHeader brandName="Example Bank" logo={<span>logo</span>} />)
    expect(screen.getByText('Example Bank')).toBeInTheDocument()
  })
})

describe('ScreenLayout', () => {
  it('renders children', () => {
    render(<ScreenLayout>Hello</ScreenLayout>)
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })
})
