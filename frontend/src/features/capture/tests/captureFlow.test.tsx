/**
 * Capture-flow tests (M2 §70). No real camera required; the fake media layer (mediaFakes.ts)
 * supplies synthetic streams, video behavior, canvas encoding and object URLs.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CaptureHarness } from './CaptureHarness'
import type { CaptureBundle } from '../types/capture'
import type { FaceDetectorProvider } from '../quality/face/FaceDetectorProvider'
import type { BundleQualityAssessment } from '../quality/types/quality'
import {
  createDeviceInfo,
  createFakeStream,
  type MediaEnvironment,
  setSecureContext,
  setupMediaEnvironment,
  removeMediaDevices,
} from './mediaFakes'
import {
  FakeFaceDetector,
  readyBundleAssessment,
  retryBundleAssessment,
  unavailableBundleAssessment,
} from './qualityFakes'

interface Harness {
  video: HTMLVideoElement
  fireLoadedMetadata: () => void
}

interface RenderHarnessOptions {
  useRvf?: boolean
  onBundleReady?: (bundle: CaptureBundle) => void
  faceDetector?: FaceDetectorProvider
  analyzeBundle?: (bundle: CaptureBundle) => Promise<BundleQualityAssessment>
}

function renderHarness(options: RenderHarnessOptions = {}): {
  env: MediaEnvironment
  h: Harness
  unmount: () => void
  detector: FakeFaceDetector
} {
  const env = setupMediaEnvironment(options)
  const detector = (options.faceDetector ?? new FakeFaceDetector()) as FakeFaceDetector
  const analyzeBundle =
    options.analyzeBundle ??
    ((bundle: CaptureBundle) => Promise.resolve(readyBundleAssessment(bundle)))
  const utils = render(
    <CaptureHarness
      onBundleReady={options.onBundleReady}
      faceDetector={detector}
      analyzeBundle={analyzeBundle}
    />,
  )
  const video = utils.container.querySelector('[data-testid="harness-video"]') as HTMLVideoElement
  const fireLoadedMetadata = () => video.dispatchEvent(new Event('loadedmetadata'))
  return { env, h: { video, fireLoadedMetadata }, unmount: utils.unmount, detector }
}

function captureStreams(env: MediaEnvironment) {
  const streams: ReturnType<typeof createFakeStream>[] = []
  env.mediaDevices.getUserMedia.mockImplementation(() => {
    const fake = createFakeStream()
    streams.push(fake)
    return Promise.resolve(fake.stream)
  })
  return streams
}

function phaseElement(): HTMLElement {
  return screen.getByTestId('phase')
}

async function startCameraToStreaming(env: MediaEnvironment, h: Harness): Promise<void> {
  fireEvent.click(screen.getByText('start'))
  await waitFor(() => expect(env.mediaDevices.getUserMedia).toHaveBeenCalled())
  await waitFor(() => expect(h.video.srcObject).not.toBeNull())
  act(() => h.fireLoadedMetadata())
  await waitFor(() => expect(phaseElement()).toHaveTextContent('streaming'))
}

async function captureToPreview(): Promise<void> {
  fireEvent.click(screen.getByText('capture'))
  await waitFor(() => expect(phaseElement()).toHaveTextContent('preview'))
}

describe('capture flow', () => {
  afterEach(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  it('grants permission, attaches the stream, and reports safe settings', async () => {
    const { env, h } = renderHarness()
    await startCameraToStreaming(env, h)

    const constraints = env.mediaDevices.getUserMedia.mock.calls[0][0]
    expect(constraints).toMatchObject({
      audio: false,
      video: {
        facingMode: { ideal: 'user' },
      },
    })
    const videoConstraints = constraints.video as MediaTrackConstraints
    expect(videoConstraints.width).toMatchObject({ ideal: 1280 })
    expect(videoConstraints.height).toMatchObject({ ideal: 720 })

    expect(phaseElement()).toHaveTextContent('streaming')
    // Safe settings only: no deviceId/groupId identifiers.
    expect(screen.getByTestId('can-switch')).toHaveTextContent('false')
  })

  it('fails with INSECURE_CONTEXT without calling getUserMedia', async () => {
    const { env } = renderHarness()
    setSecureContext(false)
    fireEvent.click(screen.getByText('start'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('INSECURE_CONTEXT'),
    )
    expect(env.mediaDevices.getUserMedia).not.toHaveBeenCalled()
  })

  it('fails with CAMERA_API_UNAVAILABLE when mediaDevices is missing', async () => {
    renderHarness()
    removeMediaDevices()
    fireEvent.click(screen.getByText('start'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('CAMERA_API_UNAVAILABLE'),
    )
  })

  it('maps permission denial to CAMERA_PERMISSION_DENIED', async () => {
    const { env } = renderHarness()
    env.mediaDevices.getUserMedia.mockRejectedValue(new DOMException('denied', 'NotAllowedError'))
    fireEvent.click(screen.getByText('start'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('CAMERA_PERMISSION_DENIED'),
    )
    expect(phaseElement()).toHaveTextContent('error')
  })

  it('maps camera-not-found to CAMERA_NOT_FOUND', async () => {
    const { env } = renderHarness()
    env.mediaDevices.getUserMedia.mockRejectedValue(new DOMException('nope', 'NotFoundError'))
    fireEvent.click(screen.getByText('start'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('CAMERA_NOT_FOUND'),
    )
  })

  it('maps a busy camera to CAMERA_IN_USE_OR_UNREADABLE', async () => {
    const { env } = renderHarness()
    env.mediaDevices.getUserMedia.mockRejectedValue(new DOMException('busy', 'NotReadableError'))
    fireEvent.click(screen.getByText('start'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('CAMERA_IN_USE_OR_UNREADABLE'),
    )
  })

  it('captures an 8-frame burst and selects the middle representative frame', async () => {
    const bundles: unknown[] = []
    const { env, h } = renderHarness({ onBundleReady: (bundle) => bundles.push(bundle) })
    await startCameraToStreaming(env, h)

    fireEvent.click(screen.getByText('capture'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('preview'))

    expect(env.canvas.toBlob).toHaveBeenCalledTimes(8)
    expect(screen.getByTestId('preview-img')).toBeInTheDocument()

    // Confirm to receive the bundle via the M3 seam.
    fireEvent.click(screen.getByText('confirm'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('confirmed'))
    const bundle = bundles[0] as {
      frames: { id: string }[]
      representativeFrameId: string
      captureConfigVersion: string
    }
    expect(bundle.frames).toHaveLength(8)
    expect(bundle.representativeFrameId).toBe(bundle.frames[3].id)
    expect(bundle.captureConfigVersion).toBe('capture-v1')
  })

  it('uses the requestAnimationFrame fallback scheduler when rVFC is unavailable', async () => {
    const { env, h } = renderHarness({ useRvf: false })
    await startCameraToStreaming(env, h)
    await captureToPreview()
    expect(screen.getByTestId('preview-img')).toBeInTheDocument()
  })

  it('tolerates partial frame encoding failures down to the minimum', async () => {
    const { env, h } = renderHarness()
    // Frames 3 and 6 fail to encode; 6 of 8 succeed (minimum = 6).
    env.canvas.setToBlob((index) =>
      index === 3 || index === 6 ? null : new Blob(['x'], { type: 'image/jpeg' }),
    )
    await startCameraToStreaming(env, h)
    await captureToPreview()
    expect(screen.getByTestId('bundle-frames')).toHaveTextContent('6')
  })

  it('fails with INSUFFICIENT_FRAMES when too few frames encode', async () => {
    const { env, h } = renderHarness()
    const streams = captureStreams(env)
    env.canvas.setToBlob(() => null)
    await startCameraToStreaming(env, h)
    fireEvent.click(screen.getByText('capture'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('INSUFFICIENT_FRAMES'),
    )
    // Camera stream remains active and recoverable.
    expect(streams[0].track.stop).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('resume'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('streaming'))
  })

  it('fails with FRAME_CAPTURE_FAILED when the canvas context is unavailable', async () => {
    const { env, h } = renderHarness()
    env.canvas.setGetContextNull(true)
    await startCameraToStreaming(env, h)
    fireEvent.click(screen.getByText('capture'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('FRAME_CAPTURE_FAILED'),
    )
  })

  it('fails with VIDEO_NOT_READY when capturing from an uninitialized video', async () => {
    const { env, h } = renderHarness()
    await startCameraToStreaming(env, h)
    env.video.width = 0
    env.video.height = 0
    fireEvent.click(screen.getByText('capture'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('VIDEO_NOT_READY'),
    )
    expect(phaseElement()).toHaveTextContent('error')
  })

  it('switches to the rear camera, stopping the old track', async () => {
    const { env, h } = renderHarness()
    const streams = captureStreams(env)
    env.mediaDevices.enumerateDevices.mockResolvedValue([
      createDeviceInfo('videoinput', 'front'),
      createDeviceInfo('videoinput', 'back'),
    ])
    await startCameraToStreaming(env, h)
    expect(screen.getByTestId('can-switch')).toHaveTextContent('true')

    fireEvent.click(screen.getByText('switch'))
    await waitFor(() => expect(env.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(h.video.srcObject).not.toBeNull())
    act(() => h.fireLoadedMetadata())
    await waitFor(() => expect(phaseElement()).toHaveTextContent('streaming'))

    const secondConstraints = env.mediaDevices.getUserMedia.mock.calls[1][0]
    expect((secondConstraints.video as MediaTrackConstraints).facingMode).toMatchObject({
      ideal: 'environment',
    })
    expect(streams[0].track.stop).toHaveBeenCalledTimes(1)
    expect(streams[1].track.stop).not.toHaveBeenCalled()
  })

  it('ignores and stops a stale camera request that resolves after reset', async () => {
    const { env, h } = renderHarness()
    const stale = createFakeStream()
    let resolveStale: (s: MediaStream) => void = () => undefined
    env.mediaDevices.getUserMedia.mockImplementationOnce(
      () => new Promise((resolve) => (resolveStale = resolve)),
    )

    fireEvent.click(screen.getByText('start'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('requestingPermission'))
    fireEvent.click(screen.getByText('reset'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('idle'))

    act(() => resolveStale(stale.stream))
    await waitFor(() => expect(stale.track.stop).toHaveBeenCalled())
    expect(phaseElement()).toHaveTextContent('idle')
    expect(h.video.srcObject).toBeNull()
  })

  it('handles an unexpected track end as a recoverable interruption', async () => {
    const { env, h } = renderHarness()
    const streams = captureStreams(env)
    await startCameraToStreaming(env, h)

    act(() => streams[0].track.emitEnded())
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('CAMERA_INTERRUPTED'),
    )
    expect(streams[0].track.stop).toHaveBeenCalled()
    expect(phaseElement()).toHaveTextContent('error')
  })

  it('stops the camera when the document becomes hidden', async () => {
    const { env, h } = renderHarness()
    const streams = captureStreams(env)
    await startCameraToStreaming(env, h)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    act(() => document.dispatchEvent(new Event('visibilitychange')))

    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('CAMERA_INTERRUPTED'),
    )
    expect(streams[0].track.stop).toHaveBeenCalled()
  })

  it('prevents a second capture while one burst is running', async () => {
    const { env, h } = renderHarness()
    await startCameraToStreaming(env, h)
    fireEvent.click(screen.getByText('capture'))
    expect(phaseElement()).toHaveTextContent('capturing')
    fireEvent.click(screen.getByText('capture')) // ignored by the state machine
    await waitFor(() => expect(phaseElement()).toHaveTextContent('preview'))
    expect(env.canvas.toBlob).toHaveBeenCalledTimes(8)
  })

  it('retake disposes the previous preview and reacquires the camera', async () => {
    const { env, h } = renderHarness()
    const streams = captureStreams(env)
    await startCameraToStreaming(env, h)
    await captureToPreview()
    const firstPreviewUrl = screen.getByTestId('preview-img').getAttribute('src')
    expect(firstPreviewUrl).toMatch(/^blob:/)

    fireEvent.click(screen.getByText('retake'))
    await waitFor(() => expect(env.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(h.video.srcObject).not.toBeNull())
    act(() => h.fireLoadedMetadata())
    await waitFor(() => expect(screen.getByTestId('retake-count')).toHaveTextContent('1'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('streaming'))

    // Old object URL revoked, old stream stopped, new stream adopted.
    expect(env.objectUrls.revokeObjectURL).toHaveBeenCalledWith(firstPreviewUrl)
    expect(streams[0].track.stop).toHaveBeenCalled()

    await captureToPreview()
    expect(screen.getByTestId('preview-img').getAttribute('src')).toMatch(/^blob:/)
  })

  it('confirm reports the bundle through the M3 integration seam', async () => {
    const onBundleReady = vi.fn()
    const { env, h } = renderHarness({ onBundleReady })
    await startCameraToStreaming(env, h)
    await captureToPreview()
    fireEvent.click(screen.getByText('confirm'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('confirmed'))
    expect(onBundleReady).toHaveBeenCalledTimes(1)
    expect(onBundleReady.mock.calls[0][0].frames).toHaveLength(8)
  })

  it('stops tracks and revokes the preview URL on unmount', async () => {
    const { env, h, unmount } = renderHarness()
    const streams = captureStreams(env)
    await startCameraToStreaming(env, h)
    await captureToPreview()
    const previewUrl = screen.getByTestId('preview-img').getAttribute('src')

    unmount()

    expect(streams[0].track.stop).toHaveBeenCalled()
    expect(env.objectUrls.revokeObjectURL).toHaveBeenCalledWith(previewUrl)
  })

  it('recovers from a permission denial via restart', async () => {
    const { env, h } = renderHarness()
    env.mediaDevices.getUserMedia.mockRejectedValueOnce(
      new DOMException('denied', 'NotAllowedError'),
    )
    fireEvent.click(screen.getByText('start'))
    await waitFor(() =>
      expect(screen.getByTestId('error-code')).toHaveTextContent('CAMERA_PERMISSION_DENIED'),
    )

    // Second attempt succeeds.
    await startCameraToStreaming(env, h)
    expect(phaseElement()).toHaveTextContent('streaming')
  })

  it('reset returns to idle and releases everything', async () => {
    const { env, h } = renderHarness()
    const streams = captureStreams(env)
    await startCameraToStreaming(env, h)
    await captureToPreview()
    const previewUrl = screen.getByTestId('preview-img').getAttribute('src')

    fireEvent.click(screen.getByText('reset'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('idle'))
    expect(streams[0].track.stop).toHaveBeenCalled()
    expect(env.objectUrls.revokeObjectURL).toHaveBeenCalledWith(previewUrl)
    expect(screen.queryByTestId('preview-img')).not.toBeInTheDocument()
  })

  it('moves through ANALYZING and reports a QUALITY_READY disposition', async () => {
    let pendingBundle: CaptureBundle | null = null
    let resolveAnalysis: ((assessment: BundleQualityAssessment) => void) | null = null
    const { env, h } = renderHarness({
      analyzeBundle: (bundle) =>
        new Promise((resolve) => {
          pendingBundle = bundle
          resolveAnalysis = resolve
        }),
    })
    await startCameraToStreaming(env, h)

    fireEvent.click(screen.getByText('capture'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('analyzing'))
    expect(screen.getByTestId('quality-disposition')).toHaveTextContent('none')

    await act(async () => {
      resolveAnalysis?.(readyBundleAssessment(pendingBundle as CaptureBundle))
    })
    await waitFor(() => expect(phaseElement()).toHaveTextContent('preview'))
    expect(screen.getByTestId('quality-disposition')).toHaveTextContent('QUALITY_READY')
  })

  it('routes QUALITY_RETRY to the retry screen, then recovers via retake', async () => {
    let retryNext = true
    const { env, h } = renderHarness({
      analyzeBundle: async (bundle) => {
        if (retryNext) {
          retryNext = false
          return retryBundleAssessment(bundle, ['NO_FACE'])
        }
        return readyBundleAssessment(bundle)
      },
    })
    await startCameraToStreaming(env, h)

    fireEvent.click(screen.getByText('capture'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('qualityRetry'))
    expect(screen.getByTestId('quality-disposition')).toHaveTextContent('QUALITY_RETRY')
    expect(screen.getByTestId('retry-guidance')).toHaveTextContent(
      'Position your face inside the guide.',
    )

    // Retake returns to streaming with the camera still live.
    fireEvent.click(screen.getByText('retry-retake'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('streaming'))

    // Second capture is acceptable.
    await captureToPreview()
    expect(screen.getByTestId('quality-disposition')).toHaveTextContent('QUALITY_READY')
    expect(screen.getByTestId('preview-img')).toBeInTheDocument()
  })

  it('routes ANALYSIS_UNAVAILABLE to a quality error with the camera stopped', async () => {
    const { env, h } = renderHarness({
      analyzeBundle: async (bundle) => unavailableBundleAssessment(bundle),
    })
    const streams = captureStreams(env)
    await startCameraToStreaming(env, h)

    fireEvent.click(screen.getByText('capture'))
    await waitFor(() => expect(phaseElement()).toHaveTextContent('error'))
    expect(screen.getByTestId('error-code')).toHaveTextContent('QUALITY_ANALYSIS_ERROR')
    // No fabricated approval: the camera stream is released.
    expect(streams[0].track.stop).toHaveBeenCalled()
  })

  it('keeps the detector alive across the session and disposes on unmount', async () => {
    const { env, h, unmount, detector } = renderHarness()
    await startCameraToStreaming(env, h)
    await captureToPreview()
    expect(detector.initializeCalls).toBeGreaterThanOrEqual(1)
    unmount()
    expect(detector.disposeCalls).toBeGreaterThanOrEqual(1)
  })
})
