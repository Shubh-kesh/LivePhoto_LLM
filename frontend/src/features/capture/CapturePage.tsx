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

import { useCallback, useState } from 'react'

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
import type { CaptureBundle } from './types/capture'
import type { FaceDetectorProvider } from './quality/face/FaceDetectorProvider'
import type { BundleQualityAssessment } from './quality/types/quality'
import { readRuntimeConfig } from '../../lib/runtimeConfig'
import './capture.css'

type PreCameraStage = 'prepare' | 'permission'

export function CapturePage({
  faceDetector,
  analyzeBundle,
  experiment = false,
}: {
  faceDetector?: FaceDetectorProvider
  analyzeBundle?: (bundle: CaptureBundle) => Promise<BundleQualityAssessment>
  /** Development-only: render the VLM experiment panel (never shown on the customer path). */
  experiment?: boolean
}) {
  const [stage, setStage] = useState<PreCameraStage>('prepare')
  const [helpOpen, setHelpOpen] = useState(false)

  const flow = useCaptureFlow({ faceDetector, analyzeBundle })
  const isFrontCamera = flow.cameraSettings.facingMode !== 'environment'
  // VLM experiment UI: OFF by default. Shown only on the explicit dev route (in dev builds) or
  // when the runtime/public config enables it for UAT (M5.6 §2, §6, §84). Backend authority still
  // applies — the panel reports "unavailable" if the backend refuses.
  const vlmUiEnabled =
    (import.meta.env.DEV && experiment) || readRuntimeConfig().vlmExperimentUiEnabled

  const resetToPreparation = useCallback(() => {
    flow.reset()
    setStage('prepare')
    setHelpOpen(false)
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
      content = flow.previewUrl ? (
        <ReviewScreen
          previewUrl={flow.previewUrl}
          onRetake={() => void flow.retake()}
          onUsePhoto={flow.confirm}
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
