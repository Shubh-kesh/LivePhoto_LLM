/**
 * Pre-M6 UX IntegrationPage tests. CapturePage is mocked (jsdom must not instantiate MediaPipe
 * providers); the tests drive the integration seams the shared flow exposes: attempt registration
 * and automatic upload + portrait preparation on quality-eligible (autoProcess).
 */

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { IntegrationPage } from '../IntegrationPage'

const mockRegisterAttempt = vi.fn()
const mockUploadCapture = vi.fn()
const mockBrowserLiveness = vi.fn()
const mockWriteTestDecision = vi.fn()
const mockTriggerPortrait = vi.fn()
const mockSubmitForConsumer = vi.fn()

vi.mock('../api', () => ({
  fetchBrowserSession: vi.fn(),
  registerAttempt: (...args: unknown[]) => {
    mockRegisterAttempt(...args)
    return Promise.resolve({ attempt_count: 1, max_attempts: 10, terminal: false })
  },
  uploadCapture: (...args: unknown[]) => {
    return mockUploadCapture(...args)
  },
  browserLiveness: (...args: unknown[]) => {
    return mockBrowserLiveness(...args)
  },
  writeTestDecision: () => {
    mockWriteTestDecision()
    return Promise.resolve({})
  },
  triggerPortrait: () => {
    mockTriggerPortrait()
    return Promise.resolve({})
  },
  submitForConsumer: () => {
    return mockSubmitForConsumer()
  },
  allowlistedAttemptReason: (codes: string[]) => codes[0],
}))

import { fetchBrowserSession } from '../api'

const mockedFetch = fetchBrowserSession as unknown as ReturnType<typeof vi.fn>

interface MockCaptureProps {
  startStage?: string
  onAttempt?: (attempt: {
    attemptId: string
    disposition: 'QUALITY_RETRY' | 'QUALITY_ELIGIBLE'
    reasonCodes: string[]
  }) => void
  autoProcess?: (flow: unknown) => void | Promise<void>
}

vi.mock('../../capture/CapturePage', () => ({
  CapturePage: (props: MockCaptureProps) => (
    <div data-testid="mock-capture" data-start-stage={props.startStage}>
      <button
        type="button"
        onClick={() =>
          props.onAttempt?.({
            attemptId: 'att-1',
            disposition: 'QUALITY_ELIGIBLE',
            reasonCodes: [],
          })
        }
      >
        attempt-eligible
      </button>
      <button
        type="button"
        onClick={() =>
          props.autoProcess?.({
            bundle: {
              frames: [
                { id: 'zero', blob: new Blob(['zero']) },
                { id: 'rep', blob: new Blob(['rep']) },
              ],
              representativeFrameId: 'rep',
            },
          })
        }
      >
        auto-process
      </button>
    </div>
  ),
}))

function mockSession(state: string): void {
  mockedFetch.mockResolvedValue({ state })
}

describe('IntegrationPage', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
    mockRegisterAttempt.mockReset()
    mockUploadCapture.mockReset()
    mockBrowserLiveness.mockReset()
    mockWriteTestDecision.mockReset()
    mockTriggerPortrait.mockReset()
    mockSubmitForConsumer.mockReset()
    mockUploadCapture.mockResolvedValue({ attempt_count: 1, max_attempts: 10, terminal: false })
    mockBrowserLiveness.mockResolvedValue({
      classification: 'LIVE',
      outcome: 'PASS',
      portrait_allowed: true,
    })
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

  it('active state mounts the shared capture flow at the permission stage', async () => {
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    expect(screen.getByTestId('mock-capture')).toHaveAttribute('data-start-stage', 'permission')
  })

  it('registers QUALITY_ELIGIBLE with the attempt id and updates the attempt banner', async () => {
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    await waitFor(() =>
      expect(mockRegisterAttempt).toHaveBeenCalledWith('att-1', 'QUALITY_ELIGIBLE'),
    )
    await waitFor(() => expect(screen.getByText(/Attempt 1 of 10/)).toBeInTheDocument())
  })

  it('quality-eligible auto-uploads the selected frame (same attempt id), prepares portrait, then shows processed-portrait review', async () => {
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('auto-process').click()

    // Automatic upload of the M3-selected (representative) frame with the SAME attempt_id.
    await waitFor(() => expect(mockUploadCapture).toHaveBeenCalledTimes(1))
    const [attemptId, blob] = mockUploadCapture.mock.calls[0] as [string, Blob]
    expect(attemptId).toBe('att-1')
    // The uploaded blob is the representative frame ('rep' size 3), not the first frame ('zero' size 4).
    expect(blob.size).toBe(3)

    // Server-authoritative liveness (LIVE) is what allows portrait — not the test-PASS writer.
    await waitFor(() => expect(mockBrowserLiveness).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(mockTriggerPortrait).toHaveBeenCalledTimes(1))
    expect(mockWriteTestDecision).not.toHaveBeenCalled()

    // Processed-portrait review: title, Retry + Submit photo. No Use photo / Prepare portrait.
    await waitFor(() => expect(screen.getByText('Submit photo')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Your photo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByText('Use photo')).not.toBeInTheDocument()
    expect(screen.queryByText('Prepare portrait')).not.toBeInTheDocument()
    expect(screen.queryByText('VLM test')).not.toBeInTheDocument()
  })

  it('does not duplicate upload/liveness/portrait operations for one eligible capture', async () => {
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('auto-process').click()
    await waitFor(() => expect(screen.getByText('Submit photo')).toBeInTheDocument())
    expect(mockUploadCapture).toHaveBeenCalledTimes(1)
    expect(mockBrowserLiveness).toHaveBeenCalledTimes(1)
    expect(mockTriggerPortrait).toHaveBeenCalledTimes(1)
    expect(mockWriteTestDecision).not.toHaveBeenCalled()
  })

  it('non-LIVE liveness result blocks portrait and offers a safe Retry', async () => {
    mockBrowserLiveness.mockResolvedValueOnce({
      classification: 'SCREEN_REPLAY',
      outcome: 'FAIL',
      portrait_allowed: false,
    })
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('auto-process').click()
    await waitFor(() =>
      expect(screen.getByText("We couldn't use this photo. Please try again.")).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(mockTriggerPortrait).not.toHaveBeenCalled()
    expect(screen.queryByText('Submit photo')).not.toBeInTheDocument()
  })

  it('liveness provider failure blocks portrait with a safe retry', async () => {
    mockBrowserLiveness.mockRejectedValueOnce(new Error('provider down'))
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('auto-process').click()
    await waitFor(() =>
      expect(
        screen.getByText("We couldn't verify your photo. Please try again."),
      ).toBeInTheDocument(),
    )
    expect(mockTriggerPortrait).not.toHaveBeenCalled()
  })

  it('auto-processing failure shows a safe error with Retry (back to capture)', async () => {
    mockUploadCapture.mockRejectedValueOnce(new Error('network'))
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('auto-process').click()
    await waitFor(() =>
      expect(
        screen.getByText('Your photo could not be prepared. Please try again.'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByTestId('mock-capture')).not.toBeInTheDocument()

    // Retry returns to the camera journey (fresh shared capture mount).
    screen.getByRole('button', { name: 'Retry' }).click()
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
  })

  it('Submit calls the browser submit API and submit failure keeps the portrait for retry', async () => {
    mockSubmitForConsumer.mockRejectedValueOnce(new Error('callback'))
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('auto-process').click()
    await waitFor(() => expect(screen.getByText('Submit photo')).toBeInTheDocument())

    screen.getByText('Submit photo').click()
    await waitFor(() => expect(mockSubmitForConsumer).toHaveBeenCalledTimes(1))

    // Callback/submit failure: portrait remains and Submit can be pressed again.
    await waitFor(() =>
      expect(
        screen.getByText('Your photo could not be submitted. Please try again.'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText('Submit photo')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })
})
