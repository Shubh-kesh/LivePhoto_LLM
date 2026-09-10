/**
 * Policy evaluation tests (pre-M6 minimum-version enforcement).
 *
 * For every recognized family: major > minimum -> SUPPORTED, major == minimum -> SUPPORTED,
 * major < minimum -> VERSION_TOO_OLD. Plus unknown browser / unparseable version / missing policy.
 */

import { describe, expect, it } from 'vitest'

import { detectBrowserFromUserAgent } from '../browserDetection'
import { evaluateBrowserPolicy, type BrowserSupportPolicy } from '../browserPolicy'

const POLICY: BrowserSupportPolicy = {
  policy_version: 'browser-policy-v1',
  browsers: {
    chrome: { minimum_major: 120, enabled: true },
    edge: { minimum_major: 120, enabled: true },
    firefox: { minimum_major: 120, enabled: true },
    safari: { minimum_major: 17, enabled: true },
    ios_safari: { minimum_major: 17, enabled: true },
    android_chrome: { minimum_major: 120, enabled: true },
  },
}

function browser(ua: string) {
  return detectBrowserFromUserAgent(ua)
}

describe('evaluateBrowserPolicy — version thresholds per family', () => {
  const cases: Array<{
    name: string
    ua: string
    minimum: number
    above: string
    equal: string
    below: string
  }> = [
    {
      name: 'chrome',
      ua: 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/__VER__.0.0.0 Safari/537.36',
      minimum: 120,
      above: '140',
      equal: '120',
      below: '119',
    },
    {
      name: 'edge',
      ua: 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/__VER__.0.0.0',
      minimum: 120,
      above: '140',
      equal: '120',
      below: '119',
    },
    {
      name: 'firefox',
      ua: 'Mozilla/5.0 (Windows NT 10.0; rv:__VER__.0) Gecko/20100101 Firefox/__VER__.0',
      minimum: 120,
      above: '130',
      equal: '120',
      below: '119',
    },
    {
      name: 'safari',
      ua: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/__VER__.4 Safari/605.1.15',
      minimum: 17,
      above: '18',
      equal: '17',
      below: '16',
    },
    {
      name: 'ios_safari',
      ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS __VER___4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/__VER__.4 Mobile/15E148 Safari/604.1',
      minimum: 17,
      above: '18',
      equal: '17',
      below: '16',
    },
    {
      name: 'android_chrome',
      ua: 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/__VER__.0.0.0 Mobile Safari/537.36',
      minimum: 120,
      above: '140',
      equal: '120',
      below: '119',
    },
  ]

  for (const c of cases) {
    it(`${c.name}: above minimum -> SUPPORTED`, () => {
      const decision = evaluateBrowserPolicy(browser(c.ua.replaceAll('__VER__', c.above)), POLICY)
      expect(decision.state).toBe('SUPPORTED')
      expect(decision.detectedMajorVersion).toBe(Number(c.above))
      expect(decision.requiredMajorVersion).toBe(c.minimum)
      expect(decision.policyVersion).toBe('browser-policy-v1')
    })

    it(`${c.name}: exactly at minimum -> SUPPORTED`, () => {
      const decision = evaluateBrowserPolicy(browser(c.ua.replaceAll('__VER__', c.equal)), POLICY)
      expect(decision.state).toBe('SUPPORTED')
    })

    it(`${c.name}: below minimum -> VERSION_TOO_OLD`, () => {
      const decision = evaluateBrowserPolicy(browser(c.ua.replaceAll('__VER__', c.below)), POLICY)
      expect(decision.state).toBe('VERSION_TOO_OLD')
      expect(decision.requiredMajorVersion).toBe(c.minimum)
    })
  }
})

describe('evaluateBrowserPolicy — fail-closed states', () => {
  it('unknown browser family -> UNSUPPORTED_BROWSER', () => {
    const decision = evaluateBrowserPolicy(
      browser('Mozilla/5.0 (compatible; LegacyBrowser/1.0)'),
      POLICY,
    )
    expect(decision.state).toBe('UNSUPPORTED_BROWSER')
  })

  it('recognized family disabled in policy -> UNSUPPORTED_BROWSER', () => {
    const disabled = {
      ...POLICY,
      browsers: { ...POLICY.browsers, chrome: { minimum_major: 120, enabled: false } },
    }
    const decision = evaluateBrowserPolicy(
      browser(
        'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
      ),
      disabled,
    )
    expect(decision.state).toBe('UNSUPPORTED_BROWSER')
  })

  it('recognized family with unparseable version -> VERSION_UNKNOWN (never invents a version)', () => {
    const decision = evaluateBrowserPolicy(
      browser(
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/ Safari/537.36',
      ),
      POLICY,
    )
    expect(decision.state).toBe('VERSION_UNKNOWN')
    expect(decision.detectedMajorVersion).toBeNull()
    expect(decision.requiredMajorVersion).toBe(120)
  })

  it('null policy -> POLICY_UNAVAILABLE', () => {
    const decision = evaluateBrowserPolicy(
      browser(
        'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
      ),
      null,
    )
    expect(decision.state).toBe('POLICY_UNAVAILABLE')
    expect(decision.policyVersion).toBeNull()
  })
})
