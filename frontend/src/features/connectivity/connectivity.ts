/**
 * Browser/network preflight for the capture journeys (pre-M6 connectivity gate).
 *
 * Two independent signals gate the journey BEFORE any camera permission is requested:
 *
 *  1. Browser capability preflight — feature detection of the APIs the current capture/quality
 *     implementation actually uses. Never user-agent sniffing.
 *  2. Backend reachability — GET /api/v1/info through the normal API client with a short timeout
 *     and an explicit ``cache: 'no-store'`` (a cached success is never accepted as proof of
 *     connectivity; every probe is a fresh network round-trip).
 *
 * ``navigator.onLine`` is only a hint; the backend reachability probe is authoritative.
 */

import { apiRequest } from '../../api/client'
import { infoResponseSchema } from '../../schemas/info'
import type { BrowserSupportPolicy } from './browserPolicy'

/** Short, bounded probe timeout so the gate fails fast instead of hanging the journey (3–5s). */
export const CONNECTIVITY_TIMEOUT_MS = 4000

export type ConnectivityStatus =
  | 'checking'
  | 'ready'
  | 'offline'
  | 'backend_unreachable'
  | 'browser_update_required'
  | 'unsupported'

/**
 * Stable capability issues. `INSECURE_CONTEXT` and `CAMERA_API_UNAVAILABLE` are preserved from the
 * existing capture error taxonomy; the rest describe missing platform APIs required by the current
 * capture/quality implementation.
 */
export type CapabilityIssue =
  | 'INSECURE_CONTEXT'
  | 'CAMERA_API_UNAVAILABLE'
  | 'CANVAS_API_UNAVAILABLE'
  | 'BLOB_API_UNAVAILABLE'
  | 'OBJECT_URL_UNAVAILABLE'
  | 'REQUEST_ANIMATION_FRAME_UNAVAILABLE'

export interface CapabilityResult {
  ok: boolean
  issues: CapabilityIssue[]
}

function hasFunction(value: unknown): boolean {
  return typeof value === 'function'
}

/** Feature-detect every platform API the current capture pipeline depends on (M2/M3/M5.5). */
export function checkBrowserCapabilities(): CapabilityResult {
  const issues: CapabilityIssue[] = []

  // Camera access requires a secure context (mediaErrors.checkCameraAvailability).
  if (typeof window !== 'undefined' && window.isSecureContext === false) {
    issues.push('INSECURE_CONTEXT')
  }
  const md = typeof navigator !== 'undefined' ? navigator.mediaDevices : undefined
  if (!md || !hasFunction(md.getUserMedia)) {
    issues.push('CAMERA_API_UNAVAILABLE')
  }
  // Burst frame capture relies on canvas 2D drawing + canvas.toBlob encoding (frameCapture).
  const canvasProto =
    typeof HTMLCanvasElement !== 'undefined' ? HTMLCanvasElement.prototype : undefined
  if (!canvasProto || !hasFunction(canvasProto.getContext) || !hasFunction(canvasProto.toBlob)) {
    issues.push('CANVAS_API_UNAVAILABLE')
  }
  if (typeof Blob === 'undefined') {
    issues.push('BLOB_API_UNAVAILABLE')
  }
  if (
    typeof URL === 'undefined' ||
    !hasFunction(URL.createObjectURL) ||
    !hasFunction(URL.revokeObjectURL)
  ) {
    issues.push('OBJECT_URL_UNAVAILABLE')
  }
  if (typeof window !== 'undefined' && !hasFunction(window.requestAnimationFrame)) {
    issues.push('REQUEST_ANIMATION_FRAME_UNAVAILABLE')
  }

  return { ok: issues.length === 0, issues }
}

export interface BackendInfoProbe {
  reachable: boolean
  /** Backend-supplied browser-support policy, or null when absent/unparseable (explicit absence). */
  policy: BrowserSupportPolicy | null
}

/**
 * Single GET /api/v1/info probe that satisfies BOTH backend reachability and browser-policy
 * retrieval (no second startup request). Uses the normal API client with `cache: 'no-store'` so a
 * cached success is never mistaken for connectivity and every real preflight/reload receives the
 * current server policy.
 *
 * Failure semantics (all collapse to `reachable: false` for the customer-safe "We can't connect
 * right now." UI, but they are NOT all "no internet"):
 * - transport/network failure or timeout -> the backend could not be reached,
 * - an HTTP response (any status) proves an HTTP service answered; a non-2xx `/info`, or a 2xx
 *   response that does not match the /info contract, means LivePhoto is not healthy/ready enough
 *   to proceed,
 * - a valid 2xx response with `browser_policy: null` IS reachable but reports no policy
 *   (`policy: null` -> the gate fails closed with POLICY_UNAVAILABLE).
 *
 * The probe is intentionally independent from browser-session validation: application-level
 * session errors (401/403/expired) are surfaced by their own handlers, never here.
 */
export async function probeBackendInfo(): Promise<BackendInfoProbe> {
  try {
    const data = infoResponseSchema.parse(
      await apiRequest('/api/v1/info', {
        timeoutMs: CONNECTIVITY_TIMEOUT_MS,
        cache: 'no-store',
      }),
    )
    return { reachable: true, policy: data.browser_policy ?? null }
  } catch {
    return { reachable: false, policy: null }
  }
}
