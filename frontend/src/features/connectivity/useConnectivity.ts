/**
 * useConnectivity — connectivity/capability/browser-policy preflight for the capture journeys.
 *
 * Startup states: checking -> ready | offline | backend_unreachable | browser_update_required |
 * unsupported.
 *
 * Ordering (a single /api/v1/info request satisfies backend reachability AND browser-policy
 * retrieval):
 *   capabilities -> navigator.onLine -> probe /api/v1/info -> detect browser ->
 *   evaluate against policy -> READY only when everything passes.
 *
 * Race control (epoch + single-flight + pending recheck):
 * - Every probe captures the current epoch. Any epoch that is no longer current when a probe
 *   finishes is discarded, so a stale probe can never overwrite a newer offline/online/check state.
 * - An OFFLINE event bumps the epoch immediately, invalidating any probe started before it, and
 *   sets the offline state directly. A late old-probe success can never flip the UI back to READY.
 * - An ONLINE event never sets READY itself. It always guarantees a fresh backend probe: if a probe
 *   is already in flight the request is queued (pendingRecheck) and a new probe runs as soon as the
 *   current one completes; otherwise a probe starts immediately.
 * - Only the newest valid backend probe may transition to READY.
 * - Single-flight: at most one backend probe is in flight at any time (no uncontrolled parallel
 *   probes); repeated online events collapse into a single queued recheck.
 * - React StrictMode double-effects / re-renders never start a second probe: a concurrent initial
 *   request is deduplicated (not queued), so no probe storms.
 *
 * Mid-session: whenever the preflight legitimately re-runs (reload, Check again, offline->online
 * recovery), the LATEST server policy is re-fetched (cache: no-store) and re-evaluated. A policy
 * change that blocks the current browser blocks progression (no server-side artifacts are touched).
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  probeBackendInfo,
  checkBrowserCapabilities,
  type CapabilityIssue,
  type ConnectivityStatus,
} from './connectivity'
import { detectCurrentBrowser } from './browserDetection'
import { evaluateBrowserPolicy, type PolicyDecision } from './browserPolicy'

export interface UseConnectivityResult {
  status: ConnectivityStatus
  capabilityIssues: CapabilityIssue[]
  /** Most recent policy decision (null until the first probe completes). */
  policyDecision: PolicyDecision | null
  /** True once the gate has successfully passed, so the journey may stay mounted on later drops. */
  readyOnce: boolean
  retry: () => void
}

export function useConnectivity(): UseConnectivityResult {
  const [status, setStatus] = useState<ConnectivityStatus>('checking')
  const [capabilityIssues, setCapabilityIssues] = useState<CapabilityIssue[]>([])
  const [policyDecision, setPolicyDecision] = useState<PolicyDecision | null>(null)
  const [readyOnce, setReadyOnce] = useState(false)
  //: Bumped when a newer check should supersede in-flight work (probe start, OFFLINE event).
  const epochRef = useRef(0)
  //: True while a backend probe is running; keeps probes strictly single-flight.
  const inFlightRef = useRef(false)
  //: Set when an ONLINE event arrives while a probe is in flight — a fresh probe must run after.
  const pendingRecheckRef = useRef(false)

  const runCheck = useCallback(async (): Promise<void> => {
    // Deduplicate concurrent requests (StrictMode double-effects): a probe is already running and
    // no newer verification was explicitly requested, so this request is simply dropped.
    if (inFlightRef.current) return
    const epoch = ++epochRef.current
    inFlightRef.current = true
    setStatus('checking')
    try {
      // 1. Browser capability preflight (feature detection, never UA sniffing).
      const capabilities = checkBrowserCapabilities()
      if (!capabilities.ok) {
        if (epoch === epochRef.current) {
          setCapabilityIssues(capabilities.issues)
          setStatus('unsupported')
        }
        return
      }
      // 2. navigator.onLine is a hint, not proof: if the browser already knows it is offline, do
      //    not even attempt the probe (no server-dependent work while definitely offline).
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        if (epoch === epochRef.current) {
          setStatus('offline')
        }
        return
      }
      // 3. Backend reachability + browser policy in ONE /info probe.
      const probe = await probeBackendInfo()
      if (epoch !== epochRef.current) {
        // A newer event (e.g. OFFLINE) invalidated this probe; its result must not be applied.
        return
      }
      if (!probe.reachable) {
        setStatus('backend_unreachable')
        return
      }
      // 4. Detect the browser family/version and evaluate against the server policy.
      const decision = evaluateBrowserPolicy(detectCurrentBrowser(), probe.policy)
      setPolicyDecision(decision)
      if (decision.state === 'SUPPORTED') {
        setReadyOnce(true)
        setStatus('ready')
      } else if (decision.state === 'UNSUPPORTED_BROWSER') {
        setStatus('unsupported')
      } else {
        // VERSION_TOO_OLD / VERSION_UNKNOWN / POLICY_UNAVAILABLE -> hard block.
        setStatus('browser_update_required')
      }
    } finally {
      inFlightRef.current = false
      if (pendingRecheckRef.current) {
        // An ONLINE event asked for a fresh verification while this probe was running. Run it now
        // that the slot is free. The flag is consumed so repeated events collapse into one recheck.
        pendingRecheckRef.current = false
        void runCheck()
      }
    }
  }, [])

  //: An OFFLINE event invalidates any probe started before it and shows the offline state.
  const handleOffline = useCallback((): void => {
    epochRef.current += 1
    pendingRecheckRef.current = false
    setStatus('offline')
  }, [])

  //: An ONLINE event never sets READY directly; it always guarantees a fresh backend probe.
  const handleOnline = useCallback((): void => {
    if (inFlightRef.current) {
      pendingRecheckRef.current = true
      return
    }
    void runCheck()
  }, [runCheck])

  useEffect(() => {
    void runCheck()
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [runCheck, handleOnline, handleOffline])

  const retry = useCallback((): void => {
    void runCheck()
  }, [runCheck])

  return { status, capabilityIssues, policyDecision, readyOnce, retry }
}
