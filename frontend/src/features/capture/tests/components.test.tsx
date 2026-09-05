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
import { QualityChecking } from '../components/QualityChecking'
import { QualityRetryScreen } from '../components/QualityRetryScreen'
import { CameraError } from '../media/mediaErrors'
import { QualityError } from '../quality/errors'
import { buildLiveGuidance } from '../quality/guidance/guidance'
import type { CaptureDiagnostics as CaptureDiagnosticsData } from '../types/capture'
import type { BundleQualityAssessment } from '../quality/types/quality'

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

  it('uses a quality heading for quality-analysis failures, never a camera message', () => {
    render(
      <CameraErrorState
        error={new QualityError('QUALITY_ANALYSIS_ERROR')}
        canRetryStream={false}
        onRetryStream={vi.fn()}
        onRestart={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(
      screen.getByRole('heading', { name: "We couldn't check photo quality." }),
    ).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('check photo quality')
  })
})

describe('QualityChecking', () => {
  it('shows acquisition-quality progress without model jargon or percentages', () => {
    render(<QualityChecking />)
    expect(screen.getByRole('heading', { name: 'Checking photo quality…' })).toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })
})

describe('QualityRetryScreen', () => {
  it('shows one prioritized reason and retake/back actions', () => {
    const onRetake = vi.fn()
    render(
      <QualityRetryScreen
        guidance={buildLiveGuidance('TOO_FAR')}
        onRetake={onRetake}
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Photo needs to be retaken.' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Move closer to the camera.')
    screen.getByRole('button', { name: 'Retake photo' }).click()
    expect(onRetake).toHaveBeenCalledTimes(1)
  })
})

describe('CameraViewport guidance', () => {
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

  it('shows the guidance message and marks the guide state', () => {
    const { container } = render(
      <CameraViewport {...baseProps} guidance={buildLiveGuidance('TOO_FAR')} />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Move closer to the camera.')
    expect(container.querySelector('.camera-guide__oval--guidance')).not.toBeNull()
  })

  it('marks the guide ready without relying on color alone', () => {
    const { container } = render(
      <CameraViewport {...baseProps} guidance={buildLiveGuidance('READY')} />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Ready to capture.')
    expect(container.querySelector('.camera-guide__oval--ready')).not.toBeNull()
  })

  it('shows detector preparation status', () => {
    render(<CameraViewport {...baseProps} detectorStatus="LOADING" />)
    expect(screen.getByRole('status')).toHaveTextContent('Preparing quality check…')
  })
})

describe('CaptureDiagnostics quality', () => {
  it('renders quality metrics without image data', () => {
    const bundle = {
      captureId: 'c1',
      captureConfigVersion: 'capture-v1',
      qualityConfigVersion: 'quality-v1',
      frames: [],
      eligibleFrameIds: [],
      selectedFrameId: 'f1',
      selectionAlgorithmVersion: 'frame-ranking-v1',
      disposition: 'QUALITY_READY',
      reasonCodes: [],
      totalAnalysisTimeMs: 12,
    } as unknown as BundleQualityAssessment
    render(<CaptureDiagnostics diagnostics={null} quality={{ bundle }} />)
    expect(screen.getByTestId('capture-diagnostics')).toBeInTheDocument()
    expect(screen.getByText('QUALITY_READY')).toBeInTheDocument()
    expect(screen.queryByText(/blob:|base64|pixels/i)).not.toBeInTheDocument()
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
