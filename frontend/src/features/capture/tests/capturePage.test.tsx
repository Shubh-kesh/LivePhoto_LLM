/**
 * CapturePage integration test — M5.5 guided journey (M5.5 §93, §96).
 *
 * The M5.5 presentation journey (preparation -> permission explanation -> camera -> review ->
 * success) is driven on top of the unchanged M2/M3 capture-flow state machine. Tests here cover
 * the polished flow end-to-end with fakes, including refresh-to-preparation and back-cleanup.
 * No liveness language may appear.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CapturePage } from '../CapturePage'
import { setupMediaEnvironment, type MediaEnvironment } from './mediaFakes'
import { FakeFaceDetector, readyBundleAssessment, retryBundleAssessment } from './qualityFakes'
import { getVlmProviders } from '../../experiment/api'
import type { CaptureBundle } from '../types/capture'

vi.mock('../../experiment/api', () => ({
  getVlmProviders: vi.fn(),
  evaluateVlmExperiment: vi.fn(),
}))

const mockedProviders = vi.mocked(getVlmProviders)

const ORIGINAL_CONFIG = { ...window.__LIVEPHOTO_CONFIG__ }

function setVlmUiConfig(enabled: boolean): void {
  ;(window as { __LIVEPHOTO_CONFIG__?: Record<string, unknown> }).__LIVEPHOTO_CONFIG__ = {
    ...(window.__LIVEPHOTO_CONFIG__ ?? {}),
    vlmExperimentUiEnabled: enabled,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedProviders.mockResolvedValue({
    experimentEnabled: true,
    defaultProvider: 'mock',
    providers: [{ name: 'mock', model: 'mock-vision-v1' }],
  })
  if (ORIGINAL_CONFIG === undefined) {
    delete (window as { __LIVEPHOTO_CONFIG__?: Record<string, unknown> }).__LIVEPHOTO_CONFIG__
  } else {
    ;(window as { __LIVEPHOTO_CONFIG__?: Record<string, unknown> }).__LIVEPHOTO_CONFIG__ =
      ORIGINAL_CONFIG
  }
})

function renderCapturePage(options: { retryOnFirst?: boolean } = {}) {
  let calls = 0
  return render(
    <CapturePage
      faceDetector={new FakeFaceDetector()}
      analyzeBundle={(b: CaptureBundle) => {
        calls += 1
        return Promise.resolve(
          options.retryOnFirst && calls === 1
            ? retryBundleAssessment(b, ['NO_FACE'])
            : readyBundleAssessment(b),
        )
      }}
    />,
  )
}

function videoElement(): HTMLVideoElement {
  return screen.getByTestId('camera-video') as HTMLVideoElement
}

function fireLoadedMetadata(): void {
  act(() => videoElement().dispatchEvent(new Event('loadedmetadata')))
}

async function reachCamera(env: MediaEnvironment): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  await openCamera(env)
}

async function openCamera(env: MediaEnvironment): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: 'Open camera' }))
  await waitFor(() => expect(env.mediaDevices.getUserMedia).toHaveBeenCalled())
  await waitFor(() => expect(videoElement().srcObject).not.toBeNull())
  fireLoadedMetadata()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Capture photo' })).toBeInTheDocument(),
  )
}

describe('CapturePage M5.5 journey', () => {
  it('shows preparation first on a fresh visit and does not request the camera', async () => {
    const env = setupMediaEnvironment()
    renderCapturePage()
    expect(screen.getByRole('heading', { name: 'Prepare for your photo' })).toBeInTheDocument()
    expect(screen.getByText('Remove your mask')).toBeInTheDocument()
    expect(screen.getByText('Remove spectacles')).toBeInTheDocument()
    expect(screen.getByText('Find a well-lit place')).toBeInTheDocument()
    expect(env.mediaDevices.getUserMedia).not.toHaveBeenCalled()
  })

  it('runs prepare -> permission -> camera -> capture -> preview -> retake -> capture -> confirm', async () => {
    const env = setupMediaEnvironment()
    renderCapturePage()

    // Prepare -> permission explanation.
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByRole('heading', { name: 'Camera access' })).toBeInTheDocument()
    expect(screen.getByText('Your microphone will not be used.')).toBeInTheDocument()
    expect(env.mediaDevices.getUserMedia).not.toHaveBeenCalled()

    await openCamera(env)

    fireEvent.click(screen.getByRole('button', { name: 'Capture photo' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Use photo' })).toBeInTheDocument(),
    )
    expect(screen.getByRole('img', { name: 'Your captured photo preview' })).toBeInTheDocument()

    // Retake reacquires the camera.
    fireEvent.click(screen.getByRole('button', { name: 'Retake photo' }))
    await waitFor(() => expect(env.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(videoElement().srcObject).not.toBeNull())
    fireLoadedMetadata()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Capture photo' })).toBeInTheDocument(),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Capture photo' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Use photo' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Use photo' }))

    // Success is acquisition-only; no liveness/verification claim may be shown.
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Photo captured successfully' }),
      ).toBeInTheDocument(),
    )
    const body = document.body.textContent ?? ''
    for (const forbidden of [
      'Liveness successful',
      'You are verified',
      'Live human detected',
      'Spoof check passed',
      'Identity verified',
    ]) {
      expect(body).not.toContain(forbidden)
    }
  })

  it('shows quality retry with customer copy, then succeeds on retake', async () => {
    const env = setupMediaEnvironment()
    renderCapturePage({ retryOnFirst: true })
    await reachCamera(env)

    fireEvent.click(screen.getByRole('button', { name: 'Capture photo' }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: "Let's try again" })).toBeInTheDocument(),
    )
    // Reason copy, never the raw code.
    expect(screen.getByRole('alert')).toHaveTextContent("We couldn't see your face clearly.")
    expect(screen.queryByText('NO_FACE')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Capture photo' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Capture photo' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Use photo' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Use photo' }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Photo captured successfully' }),
      ).toBeInTheDocument(),
    )
  })

  it('shows a safe permission-denied error without technical wording', async () => {
    const env = setupMediaEnvironment()
    env.mediaDevices.getUserMedia.mockRejectedValue(
      new DOMException('Permission denied', 'NotAllowedError'),
    )
    renderCapturePage()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open camera' }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Camera access is blocked' })).toBeInTheDocument(),
    )
    expect(screen.getByRole('alert').textContent).toContain('Allow camera permission')
    expect(screen.queryByText('NotAllowedError')).not.toBeInTheDocument()
  })

  it('returns to preparation on reload (no capture state persists)', () => {
    setupMediaEnvironment()
    const { unmount } = renderCapturePage()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByRole('heading', { name: 'Camera access' })).toBeInTheDocument()
    unmount()

    // Fresh mount simulates a full page reload.
    renderCapturePage()
    expect(screen.getByRole('heading', { name: 'Prepare for your photo' })).toBeInTheDocument()
  })

  it('cleans up the camera stream when backing out of capture to preparation', async () => {
    const env = setupMediaEnvironment()
    renderCapturePage()
    await reachCamera(env)

    const stream = (await env.mediaDevices.getUserMedia.mock.results[0].value) as MediaStream
    const track = stream.getVideoTracks()[0] as unknown as {
      stopCount: () => number
    }
    expect(track.stopCount()).toBe(0)

    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Prepare for your photo' })).toBeInTheDocument(),
    )
    expect(track.stopCount()).toBeGreaterThan(0)
  })

  it('renders VLM diagnostics inside the Review screen when enabled (M5.6 correction)', async () => {
    const env = setupMediaEnvironment()
    setVlmUiConfig(true)
    renderCapturePage()
    await reachCamera(env)

    fireEvent.click(screen.getByRole('button', { name: 'Capture photo' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Use photo' })).toBeInTheDocument(),
    )

    // Review screen is rendered with the VLM test control.
    expect(screen.getByRole('heading', { name: 'Your photo' })).toBeInTheDocument()
    expect(screen.getByText('VLM test')).toBeInTheDocument()

    // Structural fix: the VLM panel lives INSIDE the Review screen content, not after a
    // full-viewport sibling (the reported bug was placement after .lp-screen min-height:100dvh).
    const reviewScreen = document.querySelector('.lp-screen')
    expect(reviewScreen).not.toBeNull()
    expect(reviewScreen?.querySelector('.vlm-experiment')).not.toBeNull()

    // Success stays clean: no VLM diagnostics after Use photo (M5.6 correction §7).
    fireEvent.click(screen.getByRole('button', { name: 'Use photo' }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Photo captured successfully' }),
      ).toBeInTheDocument(),
    )
    expect(screen.queryByText('VLM test')).not.toBeInTheDocument()
  })

  it('keeps the Review flow VLM-free when the experiment UI is disabled', async () => {
    const env = setupMediaEnvironment()
    setVlmUiConfig(false)
    renderCapturePage()
    await reachCamera(env)

    fireEvent.click(screen.getByRole('button', { name: 'Capture photo' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Use photo' })).toBeInTheDocument(),
    )

    // Normal M5.5 Review: no VLM test, no diagnostics slot content.
    expect(screen.getByRole('heading', { name: 'Your photo' })).toBeInTheDocument()
    expect(screen.queryByText('VLM test')).not.toBeInTheDocument()
    expect(document.querySelector('.vlm-experiment')).toBeNull()
  })
})
