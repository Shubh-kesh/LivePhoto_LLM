/**
 * M5.8 integration page at /xbiz/live_photo (M5.8 §28).
 *
 * Bootstraps the browser session and renders the appropriate UI:
 * - active       -> capture -> portrait -> Submit (server-authoritative canonical PASS).
 * - completed    -> safe terminal UI (no recapture).
 * - attempt_limit-> safe terminal UI.
 * - invalid/expired -> "link no longer available".
 *
 * All mutations are same-origin with credentials + the session-bound CSRF token. The browser never
 * sends Base64; images upload as multipart and the backend reads the processed portrait.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { Button, ScreenLayout, StatusMessage } from '../../design-system'
import { captureCopy } from '../capture/copy'
import {
  fetchBrowserSession,
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

const NEW_ATTEMPT_ID = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`

export function IntegrationPage() {
  const [phase, setPhase] = useState<Phase | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [capturing, setCapturing] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [frameUrl, setFrameUrl] = useState<string | null>(null)
  const [portraitUrl, setPortraitUrl] = useState<string | null>(null)
  const [portraitState, setPortraitState] = useState<'idle' | 'processing' | 'ready' | 'error'>(
    'idle',
  )
  const [submitting, setSubmitting] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

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

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop())
      if (frameUrl) URL.revokeObjectURL(frameUrl)
    }
  }, [frameUrl])

  const startCamera = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
      }
      setCameraReady(true)
    } catch {
      setError(captureCopy.errors.cameraStartFailed.title)
      setCameraReady(false)
    }
  }, [])

  const captureFrame = useCallback(async () => {
    const video = videoRef.current
    if (!video || !video.srcObject) return
    setCapturing(true)
    setError(null)
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.95),
    )
    if (!blob) {
      setError(captureCopy.errors.qualityInternal.title)
      setCapturing(false)
      return
    }
    const id = NEW_ATTEMPT_ID()
    try {
      await uploadCapture(id, blob)
      setFrameUrl(URL.createObjectURL(blob))
      setPortraitState('idle')
      setPortraitUrl(null)
    } catch {
      setError(captureCopy.errors.qualityInternal.body)
    } finally {
      setCapturing(false)
    }
  }, [])

  const preparePortrait = useCallback(async () => {
    setPortraitState('processing')
    setError(null)
    try {
      // Dev-only canonical PASS writer (local/test/dev) + portrait processing.
      await writeTestDecision()
      await triggerPortrait()
      setPortraitUrl('/api/v1/browser/portrait')
      setPortraitState('ready')
      setPhase((prev) => (prev ? { ...prev, submissionReady: true } : prev))
    } catch {
      setPortraitState('error')
      setError(captureCopy.errors.qualityInternal.body)
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

  return (
    <ScreenLayout>
      <h1 className="lp-title">{captureCopy.review.title}</h1>
      {phase.attemptCount >= 1 && (
        <StatusMessage variant="warning">
          Attempt {phase.attemptCount} of {phase.maxAttempts}
        </StatusMessage>
      )}
      {error && <StatusMessage variant="danger">{error}</StatusMessage>}

      {!frameUrl ? (
        <>
          <video
            ref={videoRef}
            data-testid="integration-video"
            autoPlay
            playsInline
            muted
            className="lp-review__image"
          />
          <div className="lp-review__actions">
            <Button variant="secondary" size="lg" onClick={() => void startCamera()}>
              Open camera
            </Button>
            <Button
              variant="primary"
              size="lg"
              onClick={() => void captureFrame()}
              disabled={capturing || !cameraReady}
            >
              {capturing ? 'Capturing…' : 'Capture photo'}
            </Button>
          </div>
        </>
      ) : (
        <>
          <img className="lp-review__image" src={frameUrl} alt="Captured photo preview" />
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
              <img
                className="lp-review__image"
                src={portraitUrl}
                alt="Processed portrait preview"
              />
              <div className="lp-review__actions">
                <Button
                  variant="primary"
                  size="lg"
                  onClick={() => void submit()}
                  disabled={submitting}
                >
                  {submitting ? 'Submitting…' : 'Submit photo'}
                </Button>
              </div>
            </>
          )}
        </>
      )}
    </ScreenLayout>
  )
}
