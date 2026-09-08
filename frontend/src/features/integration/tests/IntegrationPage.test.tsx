/**
 * M5.8.1 IntegrationPage tests. CapturePage is mocked (jsdom must not instantiate MediaPipe
 * providers); the tests drive the integration seams (onAttempt/onUsePhoto) the shared flow exposes
 * and verify the wiring (attempt registration, selected-frame upload, portrait/terminal advance).
 */

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { IntegrationPage } from '../IntegrationPage'

const mockRegisterAttempt = vi.fn()
const mockUploadCapture = vi.fn()
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
  writeTestDecision: () => {
    mockWriteTestDecision()
    return Promise.resolve({})
  },
  triggerPortrait: () => {
    mockTriggerPortrait()
    return Promise.resolve({})
  },
  submitForConsumer: () => {
    mockSubmitForConsumer()
    return Promise.resolve('http://localhost:3001/complete')
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
  onUsePhoto?: (flow: {
    bundle: { frames: { id: string; blob: Blob }[]; representativeFrameId: string } | null
  }) => void
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
          props.onAttempt?.({
            attemptId: 'att-1',
            disposition: 'QUALITY_RETRY',
            reasonCodes: ['EYES_CLOSED'],
          })
        }
      >
        attempt-retry
      </button>
      <button
        type="button"
        onClick={() =>
          props.onUsePhoto?.({
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
        use-photo
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
    mockWriteTestDecision.mockReset()
    mockTriggerPortrait.mockReset()
    mockSubmitForConsumer.mockReset()
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

  it('registers QUALITY_RETRY with an allowlisted reason', async () => {
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-retry').click()
    await waitFor(() =>
      expect(mockRegisterAttempt).toHaveBeenCalledWith('att-1', 'QUALITY_RETRY', 'EYES_CLOSED'),
    )
  })

  it('Use Photo uploads the SAME attempt id with the M3-selected representative frame blob, then advances to portrait', async () => {
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('use-photo').click()
    await waitFor(() => expect(mockUploadCapture).toHaveBeenCalledTimes(1))
    const [attemptId, blob] = mockUploadCapture.mock.calls[0] as [string, Blob]
    expect(attemptId).toBe('att-1') // same attempt_id, no new count
    // The uploaded blob must be the representative frame, NOT the first/arbitrary frame.
    // ('rep' blob has size 3; the 'zero' first-frame blob has size 4.)
    expect(blob.size).toBe(3)
    await waitFor(() => expect(screen.getByText('Prepare portrait')).toBeInTheDocument())
  })

  it('Use Photo upload failure stays on Review and does not mint a new attempt', async () => {
    mockUploadCapture.mockRejectedValueOnce(new Error('network'))
    mockSession('active')
    render(<IntegrationPage />)
    await waitFor(() => expect(screen.getByTestId('mock-capture')).toBeInTheDocument())
    screen.getByText('attempt-eligible').click()
    screen.getByText('use-photo').click()
    await waitFor(() =>
      expect(
        screen.getByText('Your photo could not be uploaded. Please try again.'),
      ).toBeInTheDocument(),
    )
    // No portrait stage; still on capture/Review.
    expect(screen.queryByText('Prepare portrait')).not.toBeInTheDocument()
    expect(mockUploadCapture).toHaveBeenCalledTimes(1)
  })
})
