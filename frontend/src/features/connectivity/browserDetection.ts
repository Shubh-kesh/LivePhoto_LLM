/**
 * Browser family + major-version identification (pre-M6 minimum-version policy).
 *
 * Centralized, deterministic, fixture-tested. NEVER scattered through React components.
 *
 * IMPORTANT: user-agent based detection is NOT a security boundary. It is used only for
 * compatibility/supportability/customer guidance. It is spoofable and must never influence
 * liveness decisions, PASS authorization, portrait authorization, fraud decisions, or callback
 * security (all of which remain server-authoritative).
 *
 * Ordering matters:
 * - Edge user agents contain Chrome tokens, so Edge must be matched BEFORE Chrome.
 * - iOS environments (iPhone/iPad/iPod) are matched FIRST and mapped conservatively to the
 *   Apple/iOS compatibility policy (``ios_safari``): Chrome/Firefox/Edge on iOS are NOT treated as
 *   equivalent to their desktop engines. The comparable version is the iOS OS version.
 * - Non-Chrome Chromium shells (Samsung Internet, Opera, Vivaldi) are NOT classified as Chrome —
 *   they fail closed as ``unknown`` (documented conservative behaviour).
 */

export type BrowserFamily =
  'chrome' | 'edge' | 'firefox' | 'safari' | 'ios_safari' | 'android_chrome' | 'unknown'

export interface BrowserInfo {
  family: BrowserFamily
  /** Detected major version, or null when the family is recognized but the version cannot be
   *  parsed reliably. We never invent a version. */
  majorVersion: number | null
  /** Retained for diagnostics only; never rendered to customers. */
  userAgent: string
}

const IOS_DEVICE = /\(iP(?:hone|ad|od);/
const IOS_OS_VERSION = /CPU (?:iPhone )?OS (\d+)(?:_| )/

/** Non-Chrome Chromium shells that must NOT be reported as Chrome (fail closed as unknown). */
const CHROMIUM_SHELL = /(?:SamsungBrowser|OPR|Vivaldi)\//

function parseIntOrNull(value: string): number | null {
  const n = Number.parseInt(value, 10)
  return Number.isNaN(n) ? null : n
}

/** Detect browser family + major version from a user agent string (pure, deterministic). */
export function detectBrowserFromUserAgent(userAgent: string): BrowserInfo {
  const ua = userAgent || ''

  // 1. Apple mobile (iPhone/iPad/iPod). Any WebKit engine on iOS maps conservatively to the
  //    Apple/iOS compatibility policy; the comparable version is the iOS OS version.
  if (IOS_DEVICE.test(ua)) {
    const ios = ua.match(IOS_OS_VERSION)
    return {
      family: 'ios_safari',
      majorVersion: ios ? parseIntOrNull(ios[1]) : null,
      userAgent: ua,
    }
  }

  // 2. Microsoft Edge (must precede Chrome — Edge UAs carry a Chrome token).
  const edge = ua.match(/Edg(?:A|iOS)?\/(\d+)/)
  if (edge) {
    return { family: 'edge', majorVersion: parseIntOrNull(edge[1]), userAgent: ua }
  }

  // 3. Non-Chrome Chromium shells are deliberately not classified as Chrome.
  if (CHROMIUM_SHELL.test(ua)) {
    return { family: 'unknown', majorVersion: null, userAgent: ua }
  }

  // 4. Android Chrome (only when a Chrome token is present; otherwise fail closed).
  if (/\bAndroid\b/.test(ua)) {
    if (/Chrome\//.test(ua)) {
      const chrome = ua.match(/Chrome\/(\d+)/)
      return {
        family: 'android_chrome',
        majorVersion: chrome ? parseIntOrNull(chrome[1]) : null,
        userAgent: ua,
      }
    }
    return { family: 'unknown', majorVersion: null, userAgent: ua }
  }

  // 5. Desktop Firefox.
  const firefox = ua.match(/Firefox\/(\d+)/)
  if (firefox) {
    return { family: 'firefox', majorVersion: parseIntOrNull(firefox[1]), userAgent: ua }
  }

  // 6. Desktop Chrome (must precede Safari — Chrome UAs carry a Safari token). The family is
  //    recognized from the Chrome token even when its version cannot be parsed.
  if (/Chrome\//.test(ua)) {
    const chrome = ua.match(/Chrome\/(\d+)/)
    return {
      family: 'chrome',
      majorVersion: chrome ? parseIntOrNull(chrome[1]) : null,
      userAgent: ua,
    }
  }

  // 7. Desktop Safari (Version/x + Safari token). Chrome/Edge on Apple devices are handled above
  //    and must never be misclassified as desktop Safari.
  const safari = ua.match(/Version\/(\d+)/)
  if (safari && /Safari\//.test(ua)) {
    return { family: 'safari', majorVersion: parseIntOrNull(safari[1]), userAgent: ua }
  }

  return { family: 'unknown', majorVersion: null, userAgent: ua }
}

/** Detect the CURRENT browser from navigator.userAgent. */
export function detectCurrentBrowser(): BrowserInfo {
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : ''
  return detectBrowserFromUserAgent(ua)
}
