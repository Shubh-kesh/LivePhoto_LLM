/**
 * Capture page — M5.5 banking-grade guided capture UX.
 *
 * Composes the M5.5 presentation journey (preparation -> permission explanation -> camera ->
 * quality -> review -> success) on top of the existing M2/M3 capture-flow state machine. The
 * state machine remains authoritative; presentation stages are derived from `flow.state` plus a
 * small two-step pre-camera stage. No liveness language is ever shown, and no biometric/capture
 * state is persisted (a reload returns to preparation).
 *
 * The CameraScreen (with the stable <video>) is always rendered as the first child so the video
 * node never unmounts across phase transitions (M2 §12, M3 §60). Overlay screens cover it; the
 * video stays hidden (stream still attached) through permission/analysis/retry phases.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { CameraScreen } from './components/CameraScreen'
import { ErrorScreen } from './components/ErrorScreen'
import { HelpSheet } from './components/HelpSheet'
import { PermissionScreen } from './components/PermissionScreen'
import { PreparationScreen } from './components/PreparationScreen'
import { QualityCheckingScreen } from './components/QualityCheckingScreen'
import { QualityRetryScreen } from './components/QualityRetryScreen'
import { ReviewScreen } from './components/ReviewScreen'
import { StartingCameraScreen } from './components/StartingCameraScreen'
import { SuccessScreen } from './components/SuccessScreen'
import { useCaptureFlow, type UseCaptureFlowResult } from './hooks/useCaptureFlow'
import { VlmExperimentPanel } from '../experiment/VlmExperimentPanel'
import {
  createTransaction,
  evaluateTransactionLiveness,
  processPortrait,
  transactionArtifactUrl,
} from '../experiment/api'
import type { CaptureBundle } from './types/capture'
import type { FaceDetectorProvider } from './quality/face/FaceDetectorProvider'
import type { BundleQualityAssessment } from './quality/types/quality'
import { Button, StatusMessage } from '../../design-system'
import { readRuntimeConfig } from '../../lib/runtimeConfig'
import { captureConfig } from './config/captureConfig'
import { qualityConfig } from './quality/config/qualityConfig'
import './capture.css'

type PreCameraStage = 'prepare' | 'permission'

export function CapturePage({
  faceDetector,
  analyzeBundle,
  experiment = false,
  startStage = 'prepare',
  onAttempt,
  onUsePhoto,
  autoProcess,
  autoProcessMessage = 'Preparing final photo…',
}: {
  faceDetector?: FaceDetectorProvider
  analyzeBundle?: (bundle: CaptureBundle) => Promise<BundleQualityAssessment>
  /** Development-only: render the VLM experiment panel (never shown on the customer path). */
  experiment?: boolean
  /** M5.8.1: integration seam — start directly at the permission stage (skips preparation). */
  startStage?: PreCameraStage
  /** M5.8.1: attempt-registration seam (forwarded to the shared capture flow). */
  onAttempt?: (attempt: import('./hooks/useCaptureFlow').CaptureAttempt) => void
  /** M5.8.1: override the default "Use photo" confirm for integration post-capture handling. */
  onUsePhoto?: (flow: UseCaptureFlowResult) => void | Promise<void>
  /**
   * Pre-M6 UX: when set, a quality-eligible preview is NOT shown as a raw ReviewScreen. Instead a
   * safe processing state is displayed and `autoProcess(flow)` is invoked exactly once per capture
   * attempt so the integration can upload the selected frame and prepare the processed portrait.
   */
  autoProcess?: (flow: UseCaptureFlowResult) => void | Promise<void>
  autoProcessMessage?: string
}) {
  const [stage, setStage] = useState<PreCameraStage>(startStage)
  const [helpOpen, setHelpOpen] = useState(false)

  const flow = useCaptureFlow({ faceDetector, analyzeBundle, onAttempt })
  const isFrontCamera = flow.cameraSettings.facingMode !== 'environment'
  // VLM experiment UI: OFF by default. Shown only on the explicit dev route (in dev builds) or
  // when the runtime/public config enables it for UAT (M5.6 §2, §6, §84). Backend authority still
  // applies — the panel reports "unavailable" if the backend refuses. The integrated customer
  // route never renders the panel (autoProcess bypasses the ReviewScreen diagnostics slot).
  //
  // Standalone /capture mode: VITE_VLM_EXPERIMENT_UI_ENABLED selects the review experience.
  //   true  -> current diagnostic/manual flow (raw Review + VLM test panel).
  //   false -> streamlined flow: automatic backend liveness (VLM_PROVIDER) -> portrait review.
  // This flag does NOT turn backend liveness validation on/off and does NOT affect /xbiz/live_photo
  // (which passes integration seams) or /dev/vlm-experiment (the experiment prop forces the dev UI).
  const vlmUiEnabled =
    (import.meta.env.DEV && experiment) || readRuntimeConfig().vlmExperimentUiEnabled

  const isExperimentOrIntegration = Boolean(experiment || onAttempt || onUsePhoto || autoProcess)
  const standaloneStreamlined = !isExperimentOrIntegration && !vlmUiEnabled

  const [standalonePortraitUrl, setStandalonePortraitUrl] = useState<string | null>(null)
  const [standaloneError, setStandaloneError] = useState<string | null>(null)
  const standaloneProcessedAttemptRef = useRef<string | null>(null)

  const resetToPreparation = useCallback(() => {
    flow.reset()
    setStage(startStage)
    setHelpOpen(false)
  }, [flow, startStage])

  // Guard against duplicate auto-processing (React StrictMode / re-renders): fire at most once per
  // capture attempt id. A Retake/Retry remounts this component (fresh ref), so the next eligible
  // capture triggers a new auto-process.
  const autoProcessedAttemptRef = useRef<string | null>(null)
  useEffect(() => {
    if (!autoProcess) return
    if (flow.state !== 'preview') return
    if (!flow.attemptId || flow.attemptId === autoProcessedAttemptRef.current) return
    autoProcessedAttemptRef.current = flow.attemptId
    void autoProcess(flow)
  }, [autoProcess, flow, flow.state, flow.attemptId])

  const runStandaloneAutoProcess = useCallback(async (current: UseCaptureFlowResult) => {
    setStandaloneError(null)
    setStandalonePortraitUrl(null)
    const selected = current.bundle?.frames.find(
      (frame) => frame.id === current.bundle?.representativeFrameId,
    )?.blob
    if (!selected) {
      setStandaloneError('Your photo could not be prepared. Please try again.')
      return
    }
    try {
      const created = await createTransaction(
        selected,
        captureConfig.configVersion,
        qualityConfig.configVersion,
      )
      // Server-authoritative liveness: the backend evaluates the stored capture with the configured
      // provider (VLM_PROVIDER) and persists a normalized result. The browser never decides LIVE.
      let liveness: { classification: string | null; outcome: string; portrait_allowed: boolean }
      try {
        liveness = await evaluateTransactionLiveness(created.transactionId)
      } catch {
        // Provider/network/schema failure: fail closed, no portrait.
        setStandaloneError("We couldn't verify your photo. Please try again.")
        return
      }
      if (!liveness.portrait_allowed) {
        // Non-LIVE / spoof / retry outcome: the backend keeps the portrait endpoint LIVE-gated.
        setStandaloneError("We couldn't use this photo. Please try again.")
        return
      }
      // Backend-confirmed LIVE -> the LIVE-gated experiment portrait endpoint may proceed.
      await processPortrait(created.transactionId)
      setStandalonePortraitUrl(transactionArtifactUrl(created.transactionId, 'PROCESSED_PORTRAIT'))
    } catch {
      setStandaloneError('Your photo could not be prepared. Please try again.')
    }
  }, [])

  // Standalone streamlined auto-process: at most once per attempt id (StrictMode/re-render safe).
  useEffect(() => {
    if (!standaloneStreamlined) return
    if (flow.state !== 'preview') return
    if (!flow.attemptId || flow.attemptId === standaloneProcessedAttemptRef.current) return
    standaloneProcessedAttemptRef.current = flow.attemptId
    void runStandaloneAutoProcess(flow)
  }, [standaloneStreamlined, runStandaloneAutoProcess, flow, flow.state, flow.attemptId])

  const handleStandaloneRetry = useCallback(() => {
    setStandalonePortraitUrl(null)
    setStandaloneError(null)
    void flow.retake()
  }, [flow])

  const cameraVisible = ['streaming', 'switchingCamera', 'capturing'].includes(flow.state)
  const cameraScreen = (
    <CameraScreen
      videoRef={flow.videoRef}
      isFrontCamera={isFrontCamera}
      canSwitchCamera={flow.canSwitchCamera}
      isCapturing={flow.state === 'capturing'}
      isSwitching={flow.state === 'switchingCamera'}
      captureProgress={flow.captureProgress}
      transientMessage={flow.transientMessage}
      guidance={flow.liveGuidance}
      detectorStatus={flow.detectorState}
      hidden={!cameraVisible}
      onSwitchCamera={() => void flow.switchCamera()}
      onCapture={() => void flow.capture()}
      onBack={resetToPreparation}
      onHelp={() => setHelpOpen(true)}
    />
  )

  let content: React.ReactNode = null
  switch (flow.state) {
    case 'idle':
      content =
        stage === 'prepare' ? (
          <PreparationScreen onContinue={() => setStage('permission')} />
        ) : (
          <PermissionScreen
            onOpenCamera={() => void flow.startCamera()}
            onBack={() => setStage('prepare')}
          />
        )
      break
    case 'requestingPermission':
      content = <StartingCameraScreen />
      break
    case 'streaming':
    case 'switchingCamera':
    case 'capturing':
      content = null
      break
    case 'analyzing':
      content = <QualityCheckingScreen />
      break
    case 'qualityRetry':
      content = (
        <QualityRetryScreen
          reasonCodes={flow.qualityAssessment?.reasonCodes ?? []}
          onRetake={() => void flow.retryRetake()}
          onReset={resetToPreparation}
        />
      )
      break
    case 'preview':
      if (autoProcess) {
        // Integrated customer journey: bypass the raw-capture ReviewScreen (and its VLM diagnostics
        // slot). A safe processing state is shown while autoProcess uploads + prepares the portrait.
        content = flow.previewUrl ? (
          <div className="lp-screen">
            <StatusMessage variant="info">{autoProcessMessage}</StatusMessage>
          </div>
        ) : null
        break
      }
      if (standaloneStreamlined) {
        if (standaloneError) {
          content = (
            <div className="lp-screen">
              <StatusMessage variant="danger">{standaloneError}</StatusMessage>
              <div className="lp-review__actions">
                <Button variant="secondary" size="lg" onClick={handleStandaloneRetry}>
                  Retry
                </Button>
              </div>
            </div>
          )
        } else if (standalonePortraitUrl) {
          // Processed-portrait review: no raw capture, no VLM diagnostics.
          content = (
            <div className="lp-screen">
              <h1 className="lp-title">Your photo</h1>
              <img
                className="lp-review__image"
                src={standalonePortraitUrl}
                alt="Processed portrait preview"
              />
              <div className="lp-review__actions">
                <Button variant="secondary" size="lg" onClick={handleStandaloneRetry}>
                  Retry
                </Button>
                <Button variant="primary" size="lg" onClick={() => flow.confirm()}>
                  Use photo
                </Button>
              </div>
            </div>
          )
        } else {
          content = flow.previewUrl ? (
            <div className="lp-screen">
              <StatusMessage variant="info">Preparing final photo…</StatusMessage>
            </div>
          ) : null
        }
        break
      }
      content = flow.previewUrl ? (
        <ReviewScreen
          previewUrl={flow.previewUrl}
          onRetake={() => void flow.retake()}
          onUsePhoto={() => (onUsePhoto ? void onUsePhoto(flow) : flow.confirm())}
          diagnostics={
            vlmUiEnabled && flow.bundle ? (
              <VlmExperimentPanel bundle={flow.bundle} quality={flow.qualityAssessment} />
            ) : undefined
          }
        />
      ) : null
      break
    case 'confirmed':
      content = <SuccessScreen onStartOver={resetToPreparation} />
      break
    case 'error':
      content = flow.error ? (
        <ErrorScreen
          error={flow.error}
          onRetry={flow.canRetryStream ? flow.resumeStream : () => void flow.startCamera()}
          onReset={resetToPreparation}
        />
      ) : null
      break
  }

  return (
    <main className="capture-page">
      {cameraScreen}
      {content}
      {helpOpen && cameraVisible && <HelpSheet onClose={() => setHelpOpen(false)} />}
    </main>
  )
}

export type { UseCaptureFlowResult }
