/**
 * useCaptureFlow — orchestration for the M2 camera capture experience (M2 §4, §20-23, §43-54).
 *
 * Wires the capture-flow state machine, the camera session, burst capture and preview lifecycle.
 * Side effects (permission, switching, burst, retake) are guarded by the state machine so
 * double-clicks and races cannot drive impossible combinations (M2 §52-53).
 */

import { useCallback, useEffect, useReducer, useRef, useState } from 'react'

import { captureConfig } from '../config/captureConfig'
import { createCaptureBundle } from '../media/bundle'
import { captureBurst, isVideoReady, releaseFrames } from '../media/frameCapture'
import { CameraError, checkCameraAvailability, toCameraError } from '../media/mediaErrors'
import {
  captureFlowReducer,
  initialCaptureFlowState,
  type CaptureFlowAction,
  type CaptureFlowPhase,
  type CaptureFlowState,
} from '../state/captureFlow'
import type { CaptureBundle, CaptureDiagnostics } from '../types/capture'
import type { SafeTrackSettings } from '../types/camera'
import { createObjectUrl, revokeObjectUrl } from '../utils/objectUrls'
import { useCamera } from './useCamera'

export interface UseCaptureFlowOptions {
  /** Integration seam for M3: receives the bundle when the customer confirms the photo (M2 §44). */
  onBundleReady?: (bundle: CaptureBundle) => void
}

export interface CaptureProgress {
  captured: number
  target: number
}

export interface UseCaptureFlowResult {
  state: CaptureFlowPhase
  error: CameraError | null
  transientMessage: string | null
  canRetryStream: boolean

  bundle: CaptureBundle | null
  previewUrl: string | null

  cameraSettings: SafeTrackSettings
  canSwitchCamera: boolean

  videoRef: React.RefObject<HTMLVideoElement | null>

  retakeCount: number
  captureProgress: CaptureProgress | null
  diagnostics: CaptureDiagnostics | null

  startCamera: () => Promise<void>
  switchCamera: () => Promise<void>
  capture: () => Promise<void>
  retake: () => Promise<void>
  confirm: () => void
  resumeStream: () => void
  reset: () => void
}

export function useCaptureFlow(options: UseCaptureFlowOptions = {}): UseCaptureFlowResult {
  const [state, dispatch] = useReducer(captureFlowReducer, initialCaptureFlowState)
  const stateRef = useRef<CaptureFlowState>(initialCaptureFlowState)
  const phaseRef = useRef<CaptureFlowPhase>('idle')

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  const [bundle, setBundle] = useState<CaptureBundle | null>(null)
  const bundleRef = useRef<CaptureBundle | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const previewUrlRef = useRef<string | null>(null)

  const [transientMessage, setTransientMessage] = useState<string | null>(null)
  const [canRetryStream, setCanRetryStream] = useState(false)
  const [retakeCount, setRetakeCount] = useState(0)
  const [captureProgress, setCaptureProgress] = useState<CaptureProgress | null>(null)
  const [diagnostics, setDiagnostics] = useState<CaptureDiagnostics | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const flowStartedAtRef = useRef<number | null>(null)
  const cameraStartMsRef = useRef<number | null>(null)
  const cameraSettingsRef = useRef<SafeTrackSettings>({})
  const cameraStopRef = useRef<() => void>(() => undefined)

  const onBundleReadyRef = useRef(options.onBundleReady)
  onBundleReadyRef.current = options.onBundleReady

  // Synchronous phase/state mirrors so async flows can read the latest phase after dispatch.
  const transition = useCallback((action: CaptureFlowAction): void => {
    const next = captureFlowReducer(stateRef.current, action)
    stateRef.current = next
    phaseRef.current = next.phase
    dispatch(action)
  }, [])

  // Read via a function so TypeScript does not carry stale control-flow narrowing across awaits.
  const readPhase = (): CaptureFlowPhase => phaseRef.current

  const handleTrackEnded = useCallback((): void => {
    const phase = phaseRef.current
    if (phase === 'streaming' || phase === 'switchingCamera' || phase === 'capturing') {
      abortRef.current?.abort()
      cameraStopRef.current()
      setCanRetryStream(false)
      transition({ type: 'INTERRUPTED', error: new CameraError('CAMERA_INTERRUPTED') })
    }
  }, [transition])

  const {
    settings,
    canSwitch,
    start: cameraStart,
    switchCamera: cameraSwitch,
    stop: cameraStop,
  } = useCamera({ videoRef, onTrackEnded: handleTrackEnded })
  cameraStopRef.current = cameraStop

  useEffect(() => {
    cameraSettingsRef.current = settings
  }, [settings])

  const acquireCamera = useCallback(async (): Promise<void> => {
    const availability = checkCameraAvailability()
    if (!availability.ok) {
      setCanRetryStream(false)
      transition({
        type: 'PERMISSION_ERROR',
        error: new CameraError(availability.errorCode ?? 'CAMERA_API_UNAVAILABLE'),
      })
      return
    }
    flowStartedAtRef.current = performance.now()
    try {
      await cameraStart(captureConfig.defaultFacingMode)
      if (readPhase() !== 'requestingPermission') {
        // Interrupted (e.g. visibility change) while requesting: never adopt the stale stream.
        cameraStop()
        return
      }
      cameraStartMsRef.current = performance.now() - flowStartedAtRef.current
      transition({ type: 'PERMISSION_OK' })
    } catch (caught) {
      if (readPhase() !== 'requestingPermission') return
      setCanRetryStream(false)
      transition({ type: 'PERMISSION_ERROR', error: toCameraError(caught) })
    }
  }, [cameraStart, cameraStop, transition])

  const startCamera = useCallback(async (): Promise<void> => {
    if (readPhase() !== 'idle' && readPhase() !== 'error') return
    setTransientMessage(null)
    transition({ type: 'START_CAMERA' })
    await acquireCamera()
  }, [acquireCamera, transition])

  const switchCamera = useCallback(async (): Promise<void> => {
    if (readPhase() !== 'streaming') return
    setTransientMessage(null)
    transition({ type: 'SWITCH_CAMERA' })
    try {
      await cameraSwitch()
      if (readPhase() !== 'switchingCamera') {
        cameraStop()
        return
      }
      transition({ type: 'SWITCH_OK' })
    } catch (caught) {
      if (readPhase() !== 'switchingCamera') return
      const cameraError = toCameraError(caught)
      // The current camera remains active (M2 §17); surface a recoverable message.
      setTransientMessage(cameraError.safeMessage)
      transition({ type: 'SWITCH_ERROR', error: cameraError })
    }
  }, [cameraSwitch, cameraStop, transition])

  const capture = useCallback(async (): Promise<void> => {
    if (readPhase() !== 'streaming') return
    setTransientMessage(null)
    transition({ type: 'CAPTURE' })

    const video = videoRef.current
    if (!video || !isVideoReady(video)) {
      setCanRetryStream(true)
      transition({ type: 'BURST_ERROR', error: new CameraError('VIDEO_NOT_READY') })
      return
    }
    if (!canvasRef.current) {
      canvasRef.current = document.createElement('canvas')
    }
    const controller = new AbortController()
    abortRef.current = controller
    setCaptureProgress({ captured: 0, target: captureConfig.burstFrameCount })
    const now = () => performance.now()

    try {
      const result = await captureBurst({
        video,
        canvas: canvasRef.current,
        frameCount: captureConfig.burstFrameCount,
        durationMs: captureConfig.burstDurationMs,
        minimumSuccessfulFrames: captureConfig.minimumSuccessfulFrames,
        mimeType: captureConfig.imageFormat,
        quality: captureConfig.jpegQuality,
        signal: controller.signal,
        onProgress: (captured) =>
          setCaptureProgress({ captured, target: captureConfig.burstFrameCount }),
        now,
      })

      if (readPhase() !== 'capturing') {
        releaseFrames(result.frames)
        return
      }

      const camera = cameraSettingsRef.current
      const nextBundle = createCaptureBundle({ frames: result.frames, camera })
      const representative = result.frames.find((f) => f.id === nextBundle.representativeFrameId)
      if (!representative) {
        releaseFrames(result.frames)
        throw new CameraError('FRAME_CAPTURE_FAILED')
      }

      const url = createObjectUrl(representative.blob)
      bundleRef.current = nextBundle
      previewUrlRef.current = url
      setBundle(nextBundle)
      setPreviewUrl(url)

      // Stop the camera while the customer reviews the photo (M2 §42).
      cameraStop()

      const totalFlowMs = flowStartedAtRef.current ? now() - flowStartedAtRef.current : null
      const totalBytes = result.frames.reduce((sum, f) => sum + f.byteSize, 0)
      setDiagnostics({
        cameraStartMs: cameraStartMsRef.current,
        burstDurationMs: result.durationMs,
        totalFlowMs,
        frameCount: result.frames.length,
        totalBytes,
        width: camera.width ?? null,
        height: camera.height ?? null,
        frameRate: camera.frameRate ?? null,
        facingMode: camera.facingMode ?? null,
        scheduler: result.scheduler,
      })
      transition({ type: 'BURST_OK' })
    } catch (caught) {
      if (controller.signal.aborted) return // handled by the interruption path
      setCanRetryStream(true)
      transition({ type: 'BURST_ERROR', error: toCameraError(caught) })
    } finally {
      setCaptureProgress(null)
      abortRef.current = null
    }
  }, [cameraStop, transition])

  const retake = useCallback(async (): Promise<void> => {
    if (readPhase() !== 'preview') return
    revokeObjectUrl(previewUrlRef.current)
    previewUrlRef.current = null
    setPreviewUrl(null)
    bundleRef.current = null
    setBundle(null)
    setRetakeCount((count) => count + 1)
    transition({ type: 'RETAKE' })
    await acquireCamera()
  }, [acquireCamera, transition])

  const confirm = useCallback((): void => {
    if (readPhase() !== 'preview') return
    transition({ type: 'CONFIRM' })
    if (onBundleReadyRef.current && bundleRef.current) {
      onBundleReadyRef.current(bundleRef.current)
    }
  }, [transition])

  const resumeStream = useCallback((): void => {
    if (readPhase() !== 'error') return
    setTransientMessage(null)
    transition({ type: 'RESUME_STREAM' })
  }, [transition])

  const reset = useCallback((): void => {
    abortRef.current?.abort()
    abortRef.current = null
    cameraStop()
    revokeObjectUrl(previewUrlRef.current)
    previewUrlRef.current = null
    setPreviewUrl(null)
    bundleRef.current = null
    setBundle(null)
    setCaptureProgress(null)
    setTransientMessage(null)
    setCanRetryStream(false)
    setRetakeCount(0)
    setDiagnostics(null)
    flowStartedAtRef.current = null
    cameraStartMsRef.current = null
    transition({ type: 'RESET' })
  }, [cameraStop, transition])

  // Visibility/privacy handling: release the camera and invalidate any unfinished burst when the
  // document becomes hidden; require explicit resume (M2 §49).
  const handleVisibilityChange = useCallback((): void => {
    if (document.visibilityState !== 'hidden') return
    const phase = phaseRef.current
    if (phase === 'idle' || phase === 'preview' || phase === 'confirmed' || phase === 'error') {
      return
    }
    abortRef.current?.abort()
    cameraStop()
    setCanRetryStream(false)
    transition({ type: 'INTERRUPTED', error: new CameraError('CAMERA_INTERRUPTED') })
  }, [cameraStop, transition])

  const handlePageHide = useCallback((): void => {
    abortRef.current?.abort()
    cameraStop()
  }, [cameraStop])

  useEffect(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('pagehide', handlePageHide)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('pagehide', handlePageHide)
    }
  }, [handleVisibilityChange, handlePageHide])

  // Primary unmount cleanup: revoke the preview object URL; the camera is stopped by useCamera.
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      revokeObjectUrl(previewUrlRef.current)
    }
  }, [])

  return {
    state: state.phase,
    error: state.error,
    transientMessage,
    canRetryStream,
    bundle,
    previewUrl,
    cameraSettings: settings,
    canSwitchCamera: canSwitch,
    videoRef,
    retakeCount,
    captureProgress,
    diagnostics,
    startCamera,
    switchCamera,
    capture,
    retake,
    confirm,
    resumeStream,
    reset,
  }
}
