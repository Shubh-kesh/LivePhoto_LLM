/**
 * Component tests for the capture UI (M2 §13, §17, §40, §55-59): mirroring, guide, controls,
 * preview, error state, diagnostics. Pure rendering tests; no media required.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CameraErrorState } from '../components/CameraErrorState'
import { CameraIntroduction } from '../components/CameraIntroduction'
import { CameraViewport } from '../components/CameraViewport'
import { CaptureDiagnostics } from '../components/CaptureDiagnostics'
import { CapturePreview } from '../components/CapturePreview'
import { CameraError } from '../media/mediaErrors'
import type { CaptureDiagnostics as CaptureDiagnosticsData } from '../types/capture'

function makeVideoRef() {
  return { current: document.createElement('video') }
}

describe('CameraIntroduction', () => {
  it('requests camera access only after an explicit user action', () => {
    const onStart = vi.fn()
    render(<CameraIntroduction onStart={onStart} pending={false} />)
    expect(
      screen.getByRole('heading', { name: /We need access to your camera/i }),
    ).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Start camera' })
    button.click()
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it('disables the button while permission is being requested', () => {
    render(<CameraIntroduction onStart={vi.fn()} pending />)
    expect(screen.getByRole('button', { name: 'Requesting camera access…' })).toBeDisabled()
  })
})

describe('CameraViewport', () => {
  const baseProps = {
    videoRef: makeVideoRef(),
    isFrontCamera: true,
    canSwitchCamera: false,
    isCapturing: false,
    isSwitching: false,
    captureProgress: null,
    transientMessage: null,
    onSwitchCamera: vi.fn(),
    onCapture: vi.fn(),
  }

  it('mirrors the front-camera preview visually only', () => {
    const { container } = render(<CameraViewport {...baseProps} isFrontCamera />)
    const video = container.querySelector('.camera-video') as HTMLElement
    expect(video).toHaveClass('camera-video--mirror')
  })

  it('does not mirror the rear-camera preview', () => {
    const { container } = render(<CameraViewport {...baseProps} isFrontCamera={false} />)
    expect(container.querySelector('.camera-video--mirror')).toBeNull()
  })

  it('renders the decorative face guide and a stable video element', () => {
    render(<CameraViewport {...baseProps} />)
    expect(screen.getByTestId('camera-video')).toBeInTheDocument()
    expect(document.querySelector('.camera-guide__oval')).not.toBeNull()
  })

  it('keeps the video mounted (hidden) while permission is requested', () => {
    const { container } = render(<CameraViewport {...baseProps} hidden />)
    expect(container.querySelector('.camera-viewport--hidden')).not.toBeNull()
    expect(screen.getByTestId('camera-video')).toBeInTheDocument()
  })

  it('hides the switch button when switching is unavailable', () => {
    render(<CameraViewport {...baseProps} canSwitchCamera={false} />)
    expect(screen.queryByRole('button', { name: 'Switch camera' })).not.toBeInTheDocument()
  })

  it('shows the switch button and disables controls while capturing', () => {
    render(<CameraViewport {...baseProps} canSwitchCamera isCapturing />)
    expect(screen.getByRole('button', { name: 'Switch camera' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Capture photo' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Hold still')
  })

  it('shows a recoverable transient message without destroying the flow', () => {
    render(<CameraViewport {...baseProps} transientMessage="We couldn't switch cameras." />)
    expect(screen.getByRole('status')).toHaveTextContent("We couldn't switch cameras.")
  })
})

describe('CapturePreview', () => {
  it('renders the preview image and retake/use actions', () => {
    render(<CapturePreview previewUrl="blob:fake-1" onRetake={vi.fn()} onConfirm={vi.fn()} />)
    expect(screen.getByRole('img', { name: 'Your captured photo preview' })).toHaveAttribute(
      'src',
      'blob:fake-1',
    )
    expect(screen.getByRole('button', { name: 'Retake photo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Use photo' })).toBeInTheDocument()
  })
})

describe('CameraErrorState', () => {
  it('shows a safe customer message, never a raw browser message', () => {
    const error = new CameraError('CAMERA_PERMISSION_DENIED', 'NotAllowedError')
    render(
      <CameraErrorState
        error={error}
        canRetryStream={false}
        onRetryStream={vi.fn()}
        onRestart={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(error.safeMessage)
    expect(screen.queryByText('NotAllowedError')).not.toBeInTheDocument()
  })

  it('offers "Try again" that resumes the stream when the camera is still active', () => {
    const onRetryStream = vi.fn()
    render(
      <CameraErrorState
        error={new CameraError('INSUFFICIENT_FRAMES')}
        canRetryStream
        onRetryStream={onRetryStream}
        onRestart={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    screen.getByRole('button', { name: 'Try again' }).click()
    expect(onRetryStream).toHaveBeenCalledTimes(1)
  })
})

describe('CaptureDiagnostics', () => {
  it('renders non-sensitive capture timing/size data in development', () => {
    const diagnostics: CaptureDiagnosticsData = {
      cameraStartMs: 120,
      burstDurationMs: 1400,
      totalFlowMs: 1900,
      frameCount: 8,
      totalBytes: 4096,
      width: 1280,
      height: 720,
      frameRate: 30,
      facingMode: 'user',
      scheduler: 'rvf',
    }
    render(<CaptureDiagnostics diagnostics={diagnostics} />)
    expect(screen.getByTestId('capture-diagnostics')).toBeInTheDocument()
    expect(screen.getByText(/1280x720 @ 30fps/)).toBeInTheDocument()
    expect(screen.queryByText(/deviceId|groupId/i)).not.toBeInTheDocument()
  })

  it('renders nothing when there is no diagnostics data', () => {
    const { container } = render(<CaptureDiagnostics diagnostics={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
