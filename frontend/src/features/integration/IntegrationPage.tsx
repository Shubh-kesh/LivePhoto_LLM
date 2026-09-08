/**
 * M5.8 integration page at /xbiz/live_photo (M5.8 §28, M5.8.1).
 *
 * Bootstraps the browser session and renders the appropriate UI:
 * - active       -> shared capture pipeline (CapturePage/useCaptureFlow) -> portrait -> Submit
 *                   (server-authoritative canonical PASS).
 * - completed    -> safe terminal UI (no recapture).
 * - attempt_limit-> safe terminal UI.
 * - invalid/expired -> "link no longer available".
 *
 * Since M5.8.1 the integrated customer route uses the SAME real capture/quality pipeline as
 * /capture (M2 burst capture, M3 quality, frame ranking, M5.7 eye gate, ReviewScreen) via the
 * shared CapturePage. This page supplies only integration-specific seams: attempt registration
 * (QUALITY_RETRY / QUALITY_ELIGIBLE with the same attempt_id) and the selected-frame upload on
 * Use Photo. All mutations are same-origin with credentials + the session-bound CSRF token.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { Button, ScreenLayout, StatusMessage } from '../../design-system'
import { CapturePage } from '../capture/CapturePage'
import type { CaptureAttempt } from '../capture/hooks/useCaptureFlow'
import {
  allowlistedAttemptReason,
  fetchBrowserSession,
  registerAttempt,
  submitForConsumer,
  triggerPortrait,
  uploadCapture,
  writeTestDecision,
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
  const [error, setError] = useState<string | null>(null)
  const [captureDone, setCaptureDone] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [portraitUrl, setPortraitUrl] = useState<string | null>(null)
  const [portraitState, setPortraitState] = useState<'idle' | 'processing' | 'ready' | 'error'>(
    'idle',
  )
  const [submitting, setSubmitting] = useState(false)
  // Current capture attempt id (minted by the shared flow per Capture press). Follows the attempt
  // through local quality analysis to the selected-frame upload. Never re-minted on upload retry.
  const attemptIdRef = useRef<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
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
      // (the later /browser/capture with the same id never double-counts).
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

  const handleUsePhoto = useCallback(
    async (flow: {
      bundle: { frames: { id: string; blob: Blob }[]; representativeFrameId: string } | null
    }) => {
      if (uploading) return
      setUploading(true)
      setError(null)
      try {
        const attemptId = attemptIdRef.current
        const selected = flow.bundle?.frames.find(
          (frame) => frame.id === flow.bundle?.representativeFrameId,
        )?.blob
        if (!attemptId || !selected) {
          setError('Your photo could not be uploaded. Please try again.')
          return
        }
        await uploadCapture(attemptId, selected)
        setCaptureDone(true)
      } catch {
        // Stay on Review; do not count another attempt / mint a new id. User may Retake or retry.
        setError('Your photo could not be uploaded. Please try again.')
      } finally {
        setUploading(false)
      }
    },
    [uploading],
  )

  const preparePortrait = useCallback(async () => {
    setPortraitState('processing')
    setError(null)
    try {
      // Dev-only canonical PASS writer (local/test/dev) + portrait processing. VLM LIVE never
      // triggers this path; only the canonical decision does.
      await writeTestDecision()
      await triggerPortrait()
      setPortraitUrl('/api/v1/browser/portrait')
      setPortraitState('ready')
      setPhase((prev) => (prev ? { ...prev, submissionReady: true } : prev))
    } catch {
      setPortraitState('error')
      setError('Your photo could not be prepared. Please try again.')
    }
  }, [])

  const submit = useCallback(async () => {
    setSubmitting(true)
    setError(null)
    try {
      const redirectUrl = await submitForConsumer()
      window.location.assign(redirectUrl)
    } catch {
      setError('Your photo could not be submitted. Please try again.')
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

  if (!captureDone) {
    return (
      <>
        {phase.attemptCount >= 1 && (
          <StatusMessage variant="warning">
            Attempt {phase.attemptCount} of {phase.maxAttempts}
          </StatusMessage>
        )}
        {error && <StatusMessage variant="danger">{error}</StatusMessage>}
        <CapturePage
          startStage="permission"
          onAttempt={handleAttempt}
          onUsePhoto={handleUsePhoto}
        />
      </>
    )
  }

  return (
    <ScreenLayout>
      <h1 className="lp-title">Your photo</h1>
      {error && <StatusMessage variant="danger">{error}</StatusMessage>}
      {portraitState === 'idle' && (
        <div className="lp-review__actions">
          <Button variant="primary" size="lg" onClick={() => void preparePortrait()}>
            Prepare portrait
          </Button>
        </div>
      )}
      {portraitState === 'processing' && (
        <StatusMessage variant="info">Preparing final photo…</StatusMessage>
      )}
      {portraitState === 'ready' && portraitUrl && (
        <>
          <img className="lp-review__image" src={portraitUrl} alt="Processed portrait preview" />
          <div className="lp-review__actions">
            <Button variant="primary" size="lg" onClick={() => void submit()} disabled={submitting}>
              {submitting ? 'Submitting…' : 'Submit photo'}
            </Button>
          </div>
        </>
      )}
    </ScreenLayout>
  )
}
