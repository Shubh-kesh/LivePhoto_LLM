/**
 * M5.8 IntegrationPage state-rendering tests (mock the browser-session API).
 */

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { IntegrationPage } from '../IntegrationPage'

vi.mock('../api', () => ({
  fetchBrowserSession: vi.fn(),
  submitForConsumer: vi.fn(),
  triggerPortrait: vi.fn(),
  uploadCapture: vi.fn(),
  writeTestDecision: vi.fn(),
}))

import { fetchBrowserSession } from '../api'

const mockedFetch = fetchBrowserSession as unknown as ReturnType<typeof vi.fn>

function mockSession(state: string): void {
  mockedFetch.mockResolvedValue({ state })
}

describe('IntegrationPage states', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
  })

  it('shows link-unavailable for invalid state', async () => {
    mockSession('invalid')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByText('Link unavailable')).toBeInTheDocument())
  })

  it('shows completed terminal UI', async () => {
    mockSession('completed')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByText('Photo complete')).toBeInTheDocument())
  })

  it('shows attempt-limit terminal UI', async () => {
    mockSession('attempt_limit')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByText('Please try again later')).toBeInTheDocument())
  })

  it('renders capture UI for active state', async () => {
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Open camera' })).toBeInTheDocument(),
    )
  })
})
