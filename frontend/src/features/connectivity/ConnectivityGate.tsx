/**
 * ConnectivityGate — reusable browser/network/policy preflight gate for /capture and
 * /xbiz/live_photo.
 *
 * The gate NEVER requests camera permission and NEVER lets the journey start before:
 *   1. the browser capability preflight passes,
 *   2. the backend is genuinely reachable (GET /api/v1/info succeeds), and
 *   3. the detected browser family/version meets the backend-supplied minimum-version policy.
 *
 * Startup blocking states (children not yet mounted):
 * - checking               -> "Checking connection…"
 * - offline                -> "No internet connection"
 * - backend_unreachable    -> "We can't connect right now."
 * - browser_update_required-> "Browser update required" (hard block, NOT dismissible)
 * - unsupported            -> "Browser not supported" (or the preserved secure-context message)
 *
 * Mid-session connectivity loss (children already mounted): a blocking overlay is shown ON TOP of
 * the still-mounted journey so recoverable frontend state (capture/transaction state, camera) is
 * preserved and no new server operations can start. Recovery only resumes after a real backend
 * probe succeeds (an `online` event alone is never sufficient). A mid-session policy recheck that
 * now blocks the browser shows the full browser-update screen (server-side artifacts are never
 * touched).
 *
 * Version detection is a compatibility/supportability gate, NOT a security boundary.
 */

import type { ReactNode } from 'react'

import { Button, ScreenLayout, StatusMessage } from '../../design-system'
import type { CapabilityIssue, ConnectivityStatus } from './connectivity'
import type { PolicyDecision } from './browserPolicy'
import { useConnectivity } from './useConnectivity'
import './connectivity.css'

export function ConnectivityGate({ children }: { children: ReactNode }) {
  const { status, capabilityIssues, policyDecision, readyOnce, retry } = useConnectivity()

  if (status === 'ready') {
    return <>{children}</>
  }

  if (status === 'unsupported') {
    return <UnsupportedScreen issues={capabilityIssues} onRetry={retry} />
  }

  if (status === 'browser_update_required') {
    // Full blocking screen, never a dismissible popup. No "Continue anyway" option.
    return <BrowserUpdateScreen decision={policyDecision} onCheckAgain={retry} />
  }

  // Initial preflight — the journey has never mounted, so a full blocking screen is shown.
  if (!readyOnce) {
    if (status === 'checking') return <CheckingScreen />
    if (status === 'offline') return <OfflineScreen onRetry={retry} />
    return <BackendUnreachableScreen onRetry={retry} />
  }

  // Mid-session loss: preserve the mounted journey under a blocking overlay.
  return (
    <>
      {children}
      <ConnectionLostOverlay status={status} onRetry={retry} />
    </>
  )
}

function CheckingScreen() {
  return (
    <ScreenLayout>
      <StatusMessage variant="info">Checking connection…</StatusMessage>
    </ScreenLayout>
  )
}

function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <ScreenLayout>
      <h1 className="lp-title">No internet connection</h1>
      <p className="lp-subtitle">Connect to the internet to continue.</p>
      <Button variant="primary" size="lg" onClick={onRetry}>
        Try again
      </Button>
    </ScreenLayout>
  )
}

function BackendUnreachableScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <ScreenLayout>
      <h1 className="lp-title">We can&apos;t connect right now.</h1>
      <p className="lp-subtitle">Check your internet connection and try again.</p>
      <Button variant="primary" size="lg" onClick={onRetry}>
        Try again
      </Button>
    </ScreenLayout>
  )
}

function BrowserUpdateScreen({
  decision,
  onCheckAgain,
}: {
  decision: PolicyDecision | null
  onCheckAgain: () => void
}) {
  // VERSION_UNKNOWN / POLICY_UNAVAILABLE cannot prove support; use the customer-safe
  // "couldn't verify" wording. Never display a raw user-agent string.
  const cannotVerify =
    decision?.state === 'VERSION_UNKNOWN' || decision?.state === 'POLICY_UNAVAILABLE'
  return (
    <ScreenLayout>
      <h1 className="lp-title">Browser update required</h1>
      <p className="lp-subtitle">
        {cannotVerify
          ? "We couldn't verify that this browser version is supported. Please update your browser or use a supported browser."
          : 'Your browser version is no longer supported. Please update your browser to continue.'}
      </p>
      <Button variant="primary" size="lg" onClick={onCheckAgain}>
        Check again
      </Button>
    </ScreenLayout>
  )
}

function UnsupportedScreen({
  issues,
  onRetry,
}: {
  issues: CapabilityIssue[]
  onRetry: () => void
}) {
  // Preserve the existing secure-context taxonomy: a real HTTPS context is a distinct, actionable
  // message; everything else falls under the general "browser not supported" policy.
  if (issues.includes('INSECURE_CONTEXT')) {
    return (
      <ScreenLayout>
        <h1 className="lp-title">Camera requires a secure connection</h1>
        <p className="lp-subtitle">Use HTTPS to open LivePhoto.</p>
      </ScreenLayout>
    )
  }
  return (
    <ScreenLayout>
      <h1 className="lp-title">Browser not supported</h1>
      <p className="lp-subtitle">
        Please use an updated version of Chrome, Edge, Firefox, or Safari.
      </p>
      <Button variant="secondary" size="lg" onClick={onRetry}>
        Try again
      </Button>
    </ScreenLayout>
  )
}

function ConnectionLostOverlay({
  status,
  onRetry,
}: {
  status: ConnectivityStatus
  onRetry: () => void
}) {
  const offline = status === 'offline'
  return (
    <div className="lp-connectivity-overlay" role={offline ? 'alert' : 'status'}>
      <div className="lp-connectivity-overlay__card">
        {status === 'checking' ? (
          <StatusMessage variant="info">Checking connection…</StatusMessage>
        ) : (
          <>
            <h1 className="lp-title">
              {offline ? 'No internet connection' : "We can't connect right now."}
            </h1>
            <p className="lp-subtitle">
              {offline
                ? 'Connect to the internet to continue.'
                : 'Check your internet connection and try again.'}
            </p>
            <Button variant="primary" size="lg" onClick={onRetry}>
              Try again
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
