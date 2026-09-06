/**
 * Component tests for the M5.5 guided-capture UI: preparation, permission, camera screen, quality
 * checking, quality retry (reason copy), review, success and error UX. Pure rendering tests; no
 * media required. M5.5 §93-94.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CameraScreen } from '../components/CameraScreen'
import { ErrorScreen } from '../components/ErrorScreen'
import { HelpSheet } from '../components/HelpSheet'
import { InstructionAnimation } from '../components/InstructionAnimation'
import { PermissionScreen } from '../components/PermissionScreen'
import { PreparationScreen } from '../components/PreparationScreen'
import { QualityCheckingScreen } from '../components/QualityCheckingScreen'
import { QualityRetryScreen } from '../components/QualityRetryScreen'
import { ReviewScreen } from '../components/ReviewScreen'
import { StartingCameraScreen } from '../components/StartingCameraScreen'
import { SuccessScreen } from '../components/SuccessScreen'
import { CameraError } from '../media/mediaErrors'
import { QualityError } from '../quality/errors'
import { buildLiveGuidance } from '../quality/guidance/guidance'

function makeVideoRef() {
  return { current: document.createElement('video') }
}

describe('PreparationScreen', () => {
  it('shows the preparation title and all four instructions on a fresh visit', () => {
    render(<PreparationScreen onContinue={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Prepare for your photo' })).toBeInTheDocument()
    expect(screen.getByText('Remove your mask')).toBeInTheDocument()
    expect(screen.getByText('Remove spectacles')).toBeInTheDocument()
    expect(screen.getByText('Keep your face clearly visible')).toBeInTheDocument()
    expect(screen.getByText('Find a well-lit place')).toBeInTheDocument()
    expect(screen.getByText('This will only take a few seconds.')).toBeInTheDocument()
  })

  it('does not show camera or liveness instructions before Continue', () => {
    render(<PreparationScreen onContinue={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Open camera' })).not.toBeInTheDocument()
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/liveness|PAD|MediaPipe|VLM/i)
  })

  it('fires Continue only on an explicit action', () => {
    const onContinue = vi.fn()
    render(<PreparationScreen onContinue={onContinue} />)
    screen.getByRole('button', { name: 'Continue' }).click()
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('never auto-requests camera access', () => {
    const { unmount } = render(<PreparationScreen onContinue={vi.fn()} />)
    expect(screen.queryByTestId('camera-video')).not.toBeInTheDocument()
    unmount()
  })
})

describe('InstructionAnimation', () => {
  it('communicates the instruction content without requiring animation', () => {
    render(<InstructionAnimation />)
    expect(screen.getByRole('img', { name: /remove your mask/i })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /remove your spectacles/i })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /centered and clearly visible/i })).toBeInTheDocument()
  })

  it('does not block the Continue action', () => {
    render(<PreparationScreen onContinue={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
  })
})

describe('PermissionScreen', () => {
  it('explains camera access before invoking getUserMedia', () => {
    const onOpen = vi.fn()
    render(<PermissionScreen onOpenCamera={onOpen} onBack={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Camera access' })).toBeInTheDocument()
    expect(screen.getByText('We need camera access to capture your photo.')).toBeInTheDocument()
    expect(screen.getByText('Your microphone will not be used.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open camera' })).toBeInTheDocument()
  })

  it('calls the camera flow only when Open camera is pressed', () => {
    const onOpen = vi.fn()
    render(<PermissionScreen onOpenCamera={onOpen} onBack={vi.fn()} />)
    expect(onOpen).not.toHaveBeenCalled()
    screen.getByRole('button', { name: 'Open camera' }).click()
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('backs to preparation', () => {
    const onBack = vi.fn()
    render(<PermissionScreen onOpenCamera={vi.fn()} onBack={onBack} />)
    screen.getByRole('button', { name: 'Back' }).click()
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})

describe('StartingCameraScreen', () => {
  it('announces the pending permission state', () => {
    render(<StartingCameraScreen />)
    expect(screen.getByRole('status')).toHaveTextContent('Starting camera…')
  })
})

describe('CameraScreen', () => {
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
    onBack: vi.fn(),
    onHelp: vi.fn(),
  }

  it('mirrors the front-camera preview visually only', () => {
    const { container } = render(<CameraScreen {...baseProps} isFrontCamera />)
    const video = container.querySelector('.camera-screen__video') as HTMLElement
    expect(video).toHaveClass('camera-screen__video--mirror')
  })

  it('does not mirror the rear-camera preview', () => {
    const { container } = render(<CameraScreen {...baseProps} isFrontCamera={false} />)
    expect(container.querySelector('.camera-screen__video--mirror')).toBeNull()
  })

  it('renders the decorative face guide and a stable video element', () => {
    render(<CameraScreen {...baseProps} />)
    expect(screen.getByTestId('camera-video')).toBeInTheDocument()
    expect(document.querySelector('.camera-screen__oval')).not.toBeNull()
  })

  it('keeps the video mounted (hidden) while permission is pending', () => {
    const { container } = render(<CameraScreen {...baseProps} hidden />)
    expect(container.querySelector('.camera-screen--hidden')).not.toBeNull()
    expect(screen.getByTestId('camera-video')).toBeInTheDocument()
  })

  it('hides the switch button when switching is unavailable', () => {
    render(<CameraScreen {...baseProps} canSwitchCamera={false} />)
    expect(screen.queryByRole('button', { name: 'Switch camera' })).not.toBeInTheDocument()
  })

  it('shows switch and capture, disabling both while capturing', () => {
    render(<CameraScreen {...baseProps} canSwitchCamera isCapturing />)
    expect(screen.getByRole('button', { name: 'Switch camera' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Capture photo' })).toBeDisabled()
    expect(screen.getAllByRole('status').some((el) => el.textContent?.includes('Hold still'))).toBe(
      true,
    )
    // No engineering frame details on the customer path.
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/Capturing frame|1\/8|burst/i)
  })

  it('shows the guidance message and marks the guide needs_attention', () => {
    const { container } = render(
      <CameraScreen {...baseProps} guidance={buildLiveGuidance('TOO_FAR')} />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Move closer to the camera.')
    expect(container.querySelector('.camera-screen__oval--needs_attention')).not.toBeNull()
  })

  it('marks the guide ready with a check, without liveness wording', () => {
    const { container } = render(
      <CameraScreen {...baseProps} guidance={buildLiveGuidance('READY')} />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Ready to capture')
    expect(container.querySelector('.camera-screen__oval--ready')).not.toBeNull()
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/Live detected|Verified|Genuine|Safe/i)
  })

  it('shows detector preparation status', () => {
    render(<CameraScreen {...baseProps} detectorStatus="LOADING" />)
    expect(screen.getByText('Preparing quality check…')).toBeInTheDocument()
  })

  it('provides back and help affordances during capture', () => {
    const onBack = vi.fn()
    const onHelp = vi.fn()
    render(<CameraScreen {...baseProps} onBack={onBack} onHelp={onHelp} />)
    screen.getByRole('button', { name: 'Back' }).click()
    screen.getByRole('button', { name: 'Help' }).click()
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(onHelp).toHaveBeenCalledTimes(1)
  })
})

describe('QualityCheckingScreen', () => {
  it('shows acquisition-quality progress without model jargon or percentages', () => {
    render(<QualityCheckingScreen />)
    expect(screen.getByRole('status')).toHaveTextContent('Checking photo quality…')
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
    expect(screen.queryByText(/MediaPipe|sharpness|confidence/i)).not.toBeInTheDocument()
  })
})

describe('QualityRetryScreen', () => {
  it('maps NO_FACE to friendly copy and never exposes the raw code', () => {
    render(<QualityRetryScreen reasonCodes={['NO_FACE']} onRetake={vi.fn()} onReset={vi.fn()} />)
    expect(screen.getByRole('heading', { name: "Let's try again" })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent("We couldn't see your face clearly.")
    expect(screen.getByRole('alert')).toHaveTextContent('Position your face inside the guide.')
    expect(screen.queryByText('NO_FACE')).not.toBeInTheDocument()
  })

  it('maps UNDEREXPOSED to a lighting action', () => {
    render(
      <QualityRetryScreen reasonCodes={['UNDEREXPOSED']} onRetake={vi.fn()} onReset={vi.fn()} />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Move to a brighter place.')
  })

  it('maps BLURRED to a steady-device action', () => {
    render(<QualityRetryScreen reasonCodes={['BLURRED']} onRetake={vi.fn()} onReset={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Hold your device steady and try again.')
  })

  it('maps MULTIPLE_FACES to a single-person action', () => {
    render(
      <QualityRetryScreen reasonCodes={['MULTIPLE_FACES']} onRetake={vi.fn()} onReset={vi.fn()} />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Make sure only one person is visible.')
  })

  it('falls back to a generic retake message for unknown failures', () => {
    render(
      <QualityRetryScreen
        reasonCodes={['QUALITY_ANALYSIS_ERROR']}
        onRetake={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent("Let's try that photo again.")
    expect(screen.queryByText('QUALITY_ANALYSIS_ERROR')).not.toBeInTheDocument()
  })

  it('fires Try again and Back to start', () => {
    const onRetake = vi.fn()
    const onReset = vi.fn()
    render(<QualityRetryScreen reasonCodes={['BLURRED']} onRetake={onRetake} onReset={onReset} />)
    screen.getByRole('button', { name: 'Try again' }).click()
    screen.getByRole('button', { name: 'Back to start' }).click()
    expect(onRetake).toHaveBeenCalledTimes(1)
    expect(onReset).toHaveBeenCalledTimes(1)
  })
})

describe('ReviewScreen', () => {
  it('renders the preview image with retake (secondary) and use-photo (primary) actions', () => {
    const onRetake = vi.fn()
    const onUse = vi.fn()
    render(<ReviewScreen previewUrl="blob:fake-1" onRetake={onRetake} onUsePhoto={onUse} />)
    expect(screen.getByRole('img', { name: 'Your captured photo preview' })).toHaveAttribute(
      'src',
      'blob:fake-1',
    )
    const retake = screen.getByRole('button', { name: 'Retake photo' })
    const use = screen.getByRole('button', { name: 'Use photo' })
    expect(retake).toHaveClass('lp-btn--secondary')
    expect(use).toHaveClass('lp-btn--primary')
    retake.click()
    use.click()
    expect(onRetake).toHaveBeenCalledTimes(1)
    expect(onUse).toHaveBeenCalledTimes(1)
  })
})

describe('SuccessScreen', () => {
  it('uses capture-success wording only', () => {
    render(<SuccessScreen onStartOver={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Photo captured successfully' })).toBeInTheDocument()
    expect(screen.getByText('Your photo is ready.')).toBeInTheDocument()
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/verified|Liveness|passed|fraud|identity/i)
  })
})

describe('ErrorScreen', () => {
  it('separates camera-permission UX from quality UX', () => {
    render(
      <ErrorScreen
        error={new CameraError('CAMERA_PERMISSION_DENIED', 'NotAllowedError')}
        onRetry={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Camera access is blocked' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Allow camera permission')
    expect(screen.queryByText('NotAllowedError')).not.toBeInTheDocument()
  })

  it('maps camera-busy to a close-other-apps message', () => {
    render(
      <ErrorScreen
        error={new CameraError('CAMERA_IN_USE_OR_UNREADABLE', 'NotReadableError')}
        onRetry={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(
      screen.getByRole('heading', { name: 'Camera is being used by another app' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Close other apps')
  })

  it('maps unsupported browsers without DOMException terminology', () => {
    render(
      <ErrorScreen
        error={new CameraError('CAMERA_API_UNAVAILABLE')}
        onRetry={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(
      screen.getByRole('heading', { name: "Camera isn't available in this browser" }),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/DOMException|NotFoundError|NotAllowedError/i),
    ).not.toBeInTheDocument()
  })

  it('keeps quality-analysis failures technically distinct from camera failures', () => {
    render(
      <ErrorScreen
        error={new QualityError('QUALITY_ANALYSIS_ERROR')}
        onRetry={vi.fn()}
        onReset={vi.fn()}
      />,
    )
    expect(
      screen.getByRole('heading', { name: 'Something went wrong while checking your photo' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Please try again.')
    expect(screen.queryByText('QUALITY_ANALYSIS_ERROR')).not.toBeInTheDocument()
  })
})

describe('HelpSheet', () => {
  it('lists non-technical help items and closes', () => {
    const onClose = vi.fn()
    render(<HelpSheet onClose={onClose} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Remove your mask')).toBeInTheDocument()
    expect(screen.getByText('Keep only one person visible')).toBeInTheDocument()
    expect(screen.queryByText(/PAD|liveness|VLM/i)).not.toBeInTheDocument()
    screen.getByRole('button', { name: 'Close' }).click()
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape without touching the camera lifecycle', () => {
    const onClose = vi.fn()
    const { unmount } = render(<HelpSheet onClose={onClose} />)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    unmount()
  })
})
