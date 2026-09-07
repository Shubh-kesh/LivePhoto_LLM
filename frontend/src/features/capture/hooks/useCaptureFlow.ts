/**
 * useCaptureFlow — orchestration for the M2/M3 camera capture experience.
 *
 * Wires the capture-flow state machine, camera session, live quality guidance, burst capture and
 * quality-based bundle analysis. Side effects are guarded by the state machine so double-clicks
 * and races cannot drive impossible combinations.
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
import { analyzeBundle } from '../quality/engine/bundleAnalyzer'
import { createFaceDetectorProvider } from '../quality/face/faceDetectorFactory'
import { createEyeStateEvaluatorProvider } from '../quality/eye/eyeStateFactory'
import type { EyeStateEvaluatorProvider } from '../quality/eye/EyeStateEvaluatorProvider'
import type {
  FaceDetectorProvider,
  FaceDetectorProviderState,
} from '../quality/face/FaceDetectorProvider'
import { QualityError } from '../quality/errors'
import {
  buildLiveGuidance,
  guidanceFromReasonCodes,
  type LiveGuidance,
} from '../quality/guidance/guidance'
import type { BundleQualityAssessment } from '../quality/types/quality'
import { createObjectUrl, revokeObjectUrl } from '../utils/objectUrls'
import { useCamera } from './useCamera'
import { useLiveQuality } from './useLiveQuality'

export interface UseCaptureFlowOptions {
  /** Integration seam for M3: receives the bundle when the customer confirms the photo. */
  onBundleReady?: (bundle: CaptureBundle) => void
  /** Face detector provider (defaults to the factory; tests inject a deterministic stub). */
  faceDetector?: FaceDetectorProvider
  /** Bundle analysis override (tests inject a deterministic result). */
  analyzeBundle?: (bundle: CaptureBundle) => Promise<BundleQualityAssessment>
}

export interface CaptureProgress {
  captured: number
  target: number
}

export interface UseCaptureFlowResult {
  state: CaptureFlowPhase
  error: CameraError | QualityError | null
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

  // M3 quality
  detectorState: FaceDetectorProviderState
  liveGuidance: LiveGuidance | null
  isLiveReady: boolean
  qualityAssessment: BundleQualityAssessment | null
  retryGuidance: LiveGuidance | null

  startCamera: () => Promise<void>
  switchCamera: () => Promise<void>
  capture: () => Promise<void>
  retake: () => Promise<void>
  retryRetake: () => Promise<void>
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
  const detectorRef = useRef<FaceDetectorProvider | null>(null)
  if (detectorRef.current === null) {
    detectorRef.current = options.faceDetector ?? createFaceDetectorProvider()
  }
  // Closed-eye gate runs frontend-only via the eye-state evaluator (M5.7 §19-22).
  const eyeEvaluatorRef = useRef<EyeStateEvaluatorProvider | null>(null)
  if (eyeEvaluatorRef.current === null) {
    eyeEvaluatorRef.current = createEyeStateEvaluatorProvider()
  }

  const [bundle, setBundle] = useState<CaptureBundle | null>(null)
  const bundleRef = useRef<CaptureBundle | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const previewUrlRef = useRef<string | null>(null)

  const [transientMessage, setTransientMessage] = useState<string | null>(null)
  const [canRetryStream, setCanRetryStream] = useState(false)
  const [retakeCount, setRetakeCount] = useState(0)
  const [captureProgress, setCaptureProgress] = useState<CaptureProgress | null>(null)
  const [diagnostics, setDiagnostics] = useState<CaptureDiagnostics | null>(null)

  const [qualityAssessment, setQualityAssessment] = useState<BundleQualityAssessment | null>(null)
  const [retryGuidance, setRetryGuidance] = useState<LiveGuidance | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const flowStartedAtRef = useRef<number | null>(null)
  const cameraStartMsRef = useRef<number | null>(null)
  const cameraSettingsRef = useRef<SafeTrackSettings>({})
  const cameraStopRef = useRef<() => void>(() => undefined)

  const onBundleReadyRef = useRef(options.onBundleReady)
  onBundleReadyRef.current = options.onBundleReady

  const analyzeBundleForFlow = useRef<(bundle: CaptureBundle) => Promise<BundleQualityAssessment>>(
    () => Promise.reject(new QualityError('QUALITY_ANALYSIS_ERROR')),
  )
  analyzeBundleForFlow.current =
    options.analyzeBundle ??
    ((b: CaptureBundle) =>
      analyzeBundle(b, {
        detector: detectorRef.current as FaceDetectorProvider,
        eyeEvaluator: eyeEvaluatorRef.current as EyeStateEvaluatorProvider,
      }))

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
    if (
      phase === 'streaming' ||
      phase === 'switchingCamera' ||
      phase === 'capturing' ||
      phase === 'analyzing'
    ) {
      abortRef.current?.abort()
      cameraStopRef.current()
      setCanRetryStream(false)
      transition({ type: 'INTERRUPTED', error: new CameraError('CAMERA_INTERRUPTED') })
    }
  }, [transition])

  const {
    settings,
    canSwitch,
    isActive,
    start: cameraStart,
    switchCamera: cameraSwitch,
    stop: cameraStop,
  } = useCamera({ videoRef, onTrackEnded: handleTrackEnded })
  cameraStopRef.current = cameraStop

  useEffect(() => {
    cameraSettingsRef.current = settings
  }, [settings])

  const liveQuality = useLiveQuality({
    videoRef,
    detector: detectorRef.current,
    eyeEvaluator: eyeEvaluatorRef.current as EyeStateEvaluatorProvider,
    enabled: state.phase === 'streaming',
  })

  // Detector + eye-evaluator lifecycle: initialize once; dispose on teardown (M3 §72-73, M5.7 §37).
  useEffect(() => {
    const detector = detectorRef.current as FaceDetectorProvider
    const eyeEvaluator = eyeEvaluatorRef.current as EyeStateEvaluatorProvider
    detector.initialize().catch(() => undefined)
    eyeEvaluator.initialize().catch(() => undefined)
    return () => {
      detector.dispose()
      eyeEvaluator.dispose()
    }
  }, [])

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
      if (isActive()) {
        // Previous camera recovered (M3 §76): recoverable message, keep streaming.
        setTransientMessage(cameraError.safeMessage)
        transition({ type: 'SWITCH_ERROR', error: cameraError })
      } else {
        // No camera left: hard error.
        setCanRetryStream(false)
        transition({ type: 'SWITCH_LOST', error: cameraError })
      }
    }
  }, [cameraSwitch, cameraStop, isActive, transition])

  const capture = useCallback(async (): Promise<void> => {
    if (readPhase() !== 'streaming') return
    setTransientMessage(null)
    transition({ type: 'CAPTURE' })

    const video = videoRef.current
    if (!video || !isVideoReady(video)) {
      setCanRetryStream(true)
      transition({ type: 'ANALYSIS_ERROR', error: new CameraError('VIDEO_NOT_READY') })
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
      transition({ type: 'BURST_COMPLETE' })

      const bundle = createCaptureBundle({
        frames: result.frames,
        camera: cameraSettingsRef.current,
      })

      const assessment = await analyzeBundleForFlow.current(bundle)
      if (readPhase() !== 'analyzing') {
        return
      }

      if (assessment.disposition === 'QUALITY_READY' && assessment.selectedFrameId) {
        // M3 §56: quality-selected representative replaces the M2 middle-frame rule.
        const updated: CaptureBundle = {
          ...bundle,
          representativeFrameId: assessment.selectedFrameId,
        }
        bundleRef.current = updated
        const representative = updated.frames.find((f) => f.id === updated.representativeFrameId)
        if (!representative) {
          releaseFrames(result.frames)
          throw new QualityError('QUALITY_ANALYSIS_ERROR')
        }
        const url = createObjectUrl(representative.blob)
        previewUrlRef.current = url
        setPreviewUrl(url)
        setBundle(updated)
        cameraStop()
        setQualityAssessment(assessment)

        const totalFlowMs = flowStartedAtRef.current ? now() - flowStartedAtRef.current : null
        const totalBytes = result.frames.reduce((sum, f) => sum + f.byteSize, 0)
        setDiagnostics({
          cameraStartMs: cameraStartMsRef.current,
          burstDurationMs: result.durationMs,
          totalFlowMs,
          frameCount: result.frames.length,
          totalBytes,
          width: cameraSettingsRef.current.width ?? null,
          height: cameraSettingsRef.current.height ?? null,
          frameRate: cameraSettingsRef.current.frameRate ?? null,
          facingMode: cameraSettingsRef.current.facingMode ?? null,
          scheduler: result.scheduler,
        })
        transition({ type: 'ANALYSIS_READY' })
      } else if (assessment.disposition === 'QUALITY_RETRY') {
        bundleRef.current = bundle
        setQualityAssessment(assessment)
        setRetryGuidance(buildLiveGuidance(guidanceFromReasonCodes(assessment.reasonCodes)))
        transition({ type: 'ANALYSIS_RETRY' })
      } else {
        cameraStop()
        setQualityAssessment(assessment)
        const code = assessment.reasonCodes.includes('FACE_ANALYSIS_UNAVAILABLE')
          ? 'FACE_ANALYSIS_UNAVAILABLE'
          : 'QUALITY_ANALYSIS_ERROR'
        transition({ type: 'ANALYSIS_ERROR', error: new QualityError(code) })
      }
    } catch (caught) {
      if (controller.signal.aborted) return // handled by the interruption path
      if (caught instanceof CameraError) {
        // Technical burst/capture failure; the camera stream is still active and recoverable.
        setCanRetryStream(true)
        transition({ type: 'ANALYSIS_ERROR', error: caught })
      } else {
        cameraStop()
        setCanRetryStream(false)
        const error =
          caught instanceof QualityError ? caught : new QualityError('QUALITY_ANALYSIS_ERROR')
        transition({ type: 'ANALYSIS_ERROR', error })
      }
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
    setQualityAssessment(null)
    setRetakeCount((count) => count + 1)
    transition({ type: 'RETAKE' })
    await acquireCamera()
  }, [acquireCamera, transition])

  const retryRetake = useCallback(async (): Promise<void> => {
    if (readPhase() !== 'qualityRetry') return
    if (bundleRef.current) releaseFrames(bundleRef.current.frames)
    bundleRef.current = null
    setBundle(null)
    setQualityAssessment(null)
    setRetryGuidance(null)
    setTransientMessage(null)
    transition({ type: 'RETRY_RETAKE' })
  }, [transition])

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
    setQualityAssessment(null)
    setRetryGuidance(null)
    flowStartedAtRef.current = null
    cameraStartMsRef.current = null
    transition({ type: 'RESET' })
  }, [cameraStop, transition])

  // Visibility/privacy handling: release the camera and invalidate any unfinished burst/analysis
  // when the document becomes hidden; require explicit resume (M2 §49).
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

  // Primary unmount cleanup: revoke the preview object URL; camera is stopped by useCamera.
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
    detectorState: liveQuality.detectorState,
    liveGuidance: liveQuality.guidance,
    isLiveReady: liveQuality.isReady,
    qualityAssessment,
    retryGuidance,
    startCamera,
    switchCamera,
    capture,
    retake,
    retryRetake,
    confirm,
    resumeStream,
    reset,
  }
}
