/**
 * M5.8 integration page at /xbiz/live_photo (M5.8 §28, M5.8.1, pre-M6 UX).
 *
 * Bootstraps the browser session and renders the appropriate UI:
 * - active       -> shared capture pipeline (CapturePage/useCaptureFlow). On quality-eligible the
 *                   selected frame is uploaded automatically, the test-only canonical PASS is
 *                   written (local/test/dev), and the processed portrait is prepared automatically.
 *                   The customer reviews the PROCESSED PORTRAIT (Retry / Submit photo).
 * - completed    -> safe terminal UI (no recapture).
 * - attempt_limit-> safe terminal UI.
 * - invalid/expired -> "link no longer available".
 *
 * All mutations are same-origin with credentials + the session-bound CSRF token. The browser never
 * sends Base64; images upload as multipart. VLM experiment diagnostics never appear on this
 * customer route (the shared flow's autoProcess bypasses the raw ReviewScreen/diagnostics slot).
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { Button, ScreenLayout, StatusMessage } from '../../design-system'
import { CapturePage } from '../capture/CapturePage'
import { livenessRetryMessage, portraitPreparationErrorMessage } from '../capture/copy'
import { selectedFaceBoxParam } from '../capture/quality/faceBox'
import type { CaptureAttempt, UseCaptureFlowResult } from '../capture/hooks/useCaptureFlow'
import {
  allowlistedAttemptReason,
  browserLiveness,
  fetchBrowserSession,
  registerAttempt,
  submitForConsumer,
  triggerPortrait,
  uploadCapture,
} from './api'

type IntegrationState = 'loading' | 'invalid' | 'expired' | 'completed' | 'attempt_limit' | 'active'

interface Phase {
  state: IntegrationState
  submissionReady: boolean
  attemptCount: number
  maxAttempts: number
  reasonCodes: string[]
}

export function IntegrationPage() {
  const [phase, setPhase] = useState<Phase | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [captureDone, setCaptureDone] = useState(false)
  const [portraitUrl, setPortraitUrl] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // Current capture attempt id (minted by the shared flow per Capture press). Follows the attempt
  // through local quality analysis to the automatic selected-frame upload. Never re-minted on
  // upload/portrait retries.
  const attemptIdRef = useRef<string | null>(null)
  // Guard against duplicate automatic upload+portrait processing from re-renders/StrictMode. The
  // shared flow already fires autoProcess at most once per attempt id; this ref is belt-and-suspenders.
  const processingRef = useRef(false)

  const load = useCallback(async () => {
    setSubmitError(null)
    try {
      const session = await fetchBrowserSession()
      setPhase({
        state: session.state,
        submissionReady: session.submission_ready ?? false,
        attemptCount: session.attempt_count ?? 0,
        maxAttempts: session.max_attempts ?? 10,
        reasonCodes: session.reason_codes ?? [],
      })
    } catch {
      setPhase({
        state: 'invalid',
        submissionReady: false,
        attemptCount: 0,
        maxAttempts: 10,
        reasonCodes: [],
      })
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const applyAttemptResponse = useCallback((body: unknown) => {
    const result = body as { attempt_count?: number; max_attempts?: number; terminal?: boolean }
    if (typeof result?.attempt_count === 'number') {
      setPhase((prev) =>
        prev
          ? {
              ...prev,
              attemptCount: result.attempt_count ?? prev.attemptCount,
              maxAttempts: result.max_attempts ?? prev.maxAttempts,
              // Server-authoritative terminal limit -> transition to the terminal UI.
              state: result.terminal ? 'attempt_limit' : prev.state,
            }
          : prev,
      )
    }
  }, [])

  const handleAttempt = useCallback(
    (attempt: CaptureAttempt) => {
      attemptIdRef.current = attempt.attemptId
      // Server registration is evidence/best-effort; at-most-once counting is guaranteed server-side
      // (the automatic /browser/capture with the same id never double-counts).
      if (attempt.disposition === 'QUALITY_RETRY') {
        registerAttempt(
          attempt.attemptId,
          'QUALITY_RETRY',
          allowlistedAttemptReason(attempt.reasonCodes),
        )
          .then(applyAttemptResponse)
          .catch(() => undefined)
      } else {
        registerAttempt(attempt.attemptId, 'QUALITY_ELIGIBLE')
          .then(applyAttemptResponse)
          .catch(() => undefined)
      }
    },
    [applyAttemptResponse],
  )

  const handleAutoProcess = useCallback(async (flow: UseCaptureFlowResult) => {
    if (processingRef.current) return
    processingRef.current = true
    setCaptureError(null)
    try {
      const attemptId = attemptIdRef.current
      const selected = flow.bundle?.frames.find(
        (frame) => frame.id === flow.bundle?.representativeFrameId,
      )?.blob
      if (!attemptId || !selected) {
        setCaptureError('Your photo could not be prepared. Please try again.')
        return
      }
      // Primary normalized face box (geometry guidance only) persisted with the capture so portrait
      // processing uses the CURRENT capture's box; also passed to the portrait request as fallback.
      const faceBox = selectedFaceBoxParam(
        flow.qualityAssessment,
        flow.bundle?.representativeFrameId,
      )
      // Automatic upload of the M3-selected frame with the SAME attempt_id (at-most-once).
      await uploadCapture(attemptId, selected, faceBox)
      // Server-authoritative liveness: the backend evaluates the stored image with the configured
      // provider (VLM_PROVIDER); the browser never chooses the provider and never writes PASS.
      // Portrait proceeds ONLY when the backend confirms LIVE (canonical PASS). No test-PASS writer.
      let liveness: {
        classification: string | null
        outcome: string
        portrait_allowed: boolean
        reason_codes?: string[]
      }
      try {
        liveness = await browserLiveness()
      } catch {
        // Provider/network/schema failure: fail closed, no portrait.
        setCaptureError("We couldn't verify your photo. Please try again.")
        return
      }
      if (!liveness.portrait_allowed) {
        // Non-LIVE / spoof / multiple-person / retry outcome: no portrait, no Submit. Safe retry
        // with a customer-facing reason (e.g. MULTIPLE_FACES) when the backend provides one.
        setCaptureError(livenessRetryMessage(liveness.reason_codes))
        return
      }
      // Portrait proceeds ONLY for backend-confirmed LIVE with the current capture's face box.
      await triggerPortrait(faceBox)
      setPortraitUrl('/api/v1/browser/portrait')
      setCaptureDone(true)
      setPhase((prev) => (prev ? { ...prev, submissionReady: true } : prev))
    } catch (caught) {
      setCaptureError(portraitPreparationErrorMessage(caught))
    } finally {
      processingRef.current = false
    }
  }, [])

  const handleRetry = useCallback(() => {
    // Return to the camera journey. A fresh CapturePage remount resets the shared flow; the next
    // physical Capture press mints a NEW attempt id. The previous portrait is not submitted.
    setCaptureDone(false)
    setCaptureError(null)
    setSubmitError(null)
    setPortraitUrl(null)
    setSubmitting(false)
    attemptIdRef.current = null
  }, [])

  const submit = useCallback(async () => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const redirectUrl = await submitForConsumer()
      window.location.assign(redirectUrl)
    } catch {
      // Keep the processed portrait visible; allow Submit to be pressed again. Not a capture attempt.
      setSubmitError('Your photo could not be submitted. Please try again.')
      setSubmitting(false)
    }
  }, [])

  if (!phase) return <ScreenLayout>Loading…</ScreenLayout>

  if (phase.state === 'invalid' || phase.state === 'expired') {
    return (
      <ScreenLayout>
        <h1 className="lp-title">Link unavailable</h1>
        <p className="lp-subtitle">This LivePhoto link is no longer available.</p>
      </ScreenLayout>
    )
  }

  if (phase.state === 'completed') {
    return (
      <ScreenLayout>
        <h1 className="lp-title">Photo complete</h1>
        <p className="lp-subtitle">Your photo has already been submitted successfully.</p>
      </ScreenLayout>
    )
  }

  if (phase.state === 'attempt_limit') {
    return (
      <ScreenLayout>
        <h1 className="lp-title">Please try again later</h1>
        <p className="lp-subtitle">You have reached the maximum number of photo attempts.</p>
      </ScreenLayout>
    )
  }

  const attemptBanner = phase.attemptCount >= 1 && (
    <StatusMessage variant="warning">
      Attempt {phase.attemptCount} of {phase.maxAttempts}
    </StatusMessage>
  )

  if (captureDone) {
    // Processed portrait review: the portrait — not the raw capture — is what the customer reviews.
    return (
      <ScreenLayout>
        <h1 className="lp-title">Your photo</h1>
        {submitError && <StatusMessage variant="danger">{submitError}</StatusMessage>}
        {portraitUrl && (
          <img className="lp-review__image" src={portraitUrl} alt="Processed portrait preview" />
        )}
        <div className="lp-review__actions">
          <Button variant="secondary" size="lg" onClick={handleRetry}>
            Retry
          </Button>
          <Button variant="primary" size="lg" onClick={() => void submit()} disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit photo'}
          </Button>
        </div>
      </ScreenLayout>
    )
  }

  if (captureError) {
    return (
      <ScreenLayout>
        <h1 className="lp-title">Your photo</h1>
        {attemptBanner}
        <StatusMessage variant="danger">{captureError}</StatusMessage>
        <div className="lp-review__actions">
          <Button variant="secondary" size="lg" onClick={handleRetry}>
            Retry
          </Button>
        </div>
      </ScreenLayout>
    )
  }

  return (
    <>
      {attemptBanner}
      <CapturePage
        startStage="permission"
        onAttempt={handleAttempt}
        autoProcess={handleAutoProcess}
      />
    </>
  )
}
