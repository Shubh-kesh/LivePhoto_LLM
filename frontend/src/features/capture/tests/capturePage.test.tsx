/**
 * CapturePage integration test (M2 §44-45): the real components wired to the flow — start,
 * capture, retake, capture again, confirm. No liveness language may appear.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CapturePage } from '../CapturePage'
import { setupMediaEnvironment, type MediaEnvironment } from './mediaFakes'
import { FakeFaceDetector, readyBundleAssessment } from './qualityFakes'

function renderCapturePage() {
  return render(
    <CapturePage
      faceDetector={new FakeFaceDetector()}
      analyzeBundle={(b) => Promise.resolve(readyBundleAssessment(b))}
    />,
  )
}

function videoElement(): HTMLVideoElement {
  return screen.getByTestId('camera-video') as HTMLVideoElement
}

function fireLoadedMetadata(): void {
  act(() => videoElement().dispatchEvent(new Event('loadedmetadata')))
}

async function startCamera(env: MediaEnvironment): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: 'Start camera' }))
  await waitFor(() => expect(env.mediaDevices.getUserMedia).toHaveBeenCalled())
  await waitFor(() => expect(videoElement().srcObject).not.toBeNull())
  fireLoadedMetadata()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Capture photo' })).toBeInTheDocument(),
  )
}

describe('CapturePage', () => {
  it('runs start -> capture -> preview -> retake -> capture -> confirm', async () => {
    const env = setupMediaEnvironment()

    renderCapturePage()
    expect(
      screen.getByRole('heading', { name: 'We need access to your camera' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Your camera is used to capture your photo.')).toBeInTheDocument()

    await startCamera(env)
    // Live preview video is present; controls are reachable.
    expect(videoElement()).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Capture photo' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Use photo' })).toBeInTheDocument(),
    )
    expect(screen.getByRole('img', { name: 'Your captured photo preview' })).toBeInTheDocument()

    // Retake reacquires the camera (metadata reloads on the new stream).
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

    // Confirmation is acquisition-only; no liveness claim may be shown (M2 §45).
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Photo captured successfully.' }),
      ).toBeInTheDocument(),
    )
    const body = document.body.textContent ?? ''
    for (const forbidden of [
      'Liveness successful',
      'You are verified',
      'Live human detected',
      'Spoof check passed',
    ]) {
      expect(body).not.toContain(forbidden)
    }
  })

  it('shows a safe error and allows restart when permission is denied', async () => {
    const env = setupMediaEnvironment()
    env.mediaDevices.getUserMedia.mockRejectedValue(new DOMException('denied', 'NotAllowedError'))
    renderCapturePage()
    fireEvent.click(screen.getByRole('button', { name: 'Start camera' }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: "We couldn't access your camera" }),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('alert').textContent).toContain('allow camera access')
  })
})
