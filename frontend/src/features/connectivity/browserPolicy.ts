/**
 * Browser support policy evaluation (pre-M6 minimum-version enforcement).
 *
 * A pure function maps a detected browser + the backend-provided policy to a typed decision.
 * Version detection is a compatibility/supportability gate, NOT a security boundary; it never
 * influences liveness/PASS/portrait/fraud/callback security.
 */

import type { BrowserFamily, BrowserInfo } from './browserDetection'

export interface BrowserPolicyEntry {
  minimum_major: number
  enabled: boolean
}

export interface BrowserSupportPolicy {
  policy_version: string
  browsers: Record<Exclude<BrowserFamily, 'unknown'>, BrowserPolicyEntry>
}

export type PolicyDecisionState =
  'SUPPORTED' | 'VERSION_TOO_OLD' | 'UNSUPPORTED_BROWSER' | 'VERSION_UNKNOWN' | 'POLICY_UNAVAILABLE'

export interface PolicyDecision {
  state: PolicyDecisionState
  /** Internal metadata — never shown verbatim to customers. */
  browserFamily: BrowserFamily
  detectedMajorVersion: number | null
  requiredMajorVersion: number | null
  policyVersion: string | null
}

/**
 * Evaluate a detected browser against the backend policy.
 *
 * - policy is null/absent           -> POLICY_UNAVAILABLE (fail closed)
 * - family unknown                  -> UNSUPPORTED_BROWSER
 * - family recognized but disabled  -> UNSUPPORTED_BROWSER
 * - recognized family + null version -> VERSION_UNKNOWN (never invent a version)
 * - version below minimum           -> VERSION_TOO_OLD
 * - otherwise                       -> SUPPORTED
 */
export function evaluateBrowserPolicy(
  browser: BrowserInfo,
  policy: BrowserSupportPolicy | null,
): PolicyDecision {
  const base = {
    browserFamily: browser.family,
    detectedMajorVersion: browser.majorVersion,
    requiredMajorVersion: null,
    policyVersion: policy?.policy_version ?? null,
  }

  if (policy === null) {
    return { ...base, state: 'POLICY_UNAVAILABLE' }
  }
  if (browser.family === 'unknown') {
    return { ...base, state: 'UNSUPPORTED_BROWSER' }
  }

  const entry = policy.browsers[browser.family]
  if (!entry || !entry.enabled) {
    return { ...base, state: 'UNSUPPORTED_BROWSER' }
  }

  const withRequired = { ...base, requiredMajorVersion: entry.minimum_major }
  if (browser.majorVersion === null) {
    return { ...withRequired, state: 'VERSION_UNKNOWN' }
  }
  if (browser.majorVersion < entry.minimum_major) {
    return { ...withRequired, state: 'VERSION_TOO_OLD' }
  }
  return { ...withRequired, state: 'SUPPORTED' }
}
