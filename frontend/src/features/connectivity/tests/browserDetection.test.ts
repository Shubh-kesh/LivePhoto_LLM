/**
 * Deterministic browser family/version detection fixtures (pre-M6 minimum-version policy).
 *
 * Covers the six required families plus important ambiguous user-agent cases:
 * - Edge must NOT be classified as Chrome,
 * - Chrome/Edge on Apple devices must NOT be classified as desktop Safari,
 * - iOS environments map conservatively to the Apple/iOS policy (ios_safari) with the iOS OS
 *   version,
 * - non-Chrome Chromium shells (Samsung/Opera/Vivaldi) fail closed as unknown,
 * - recognized family with unparseable version yields majorVersion null (never invented).
 */

import { describe, expect, it } from 'vitest'

import { detectBrowserFromUserAgent } from '../browserDetection'

const CHROME_DESKTOP =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
const EDGE_DESKTOP =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0'
const FIREFOX_DESKTOP =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0'
const SAFARI_DESKTOP =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15'
const CHROME_ANDROID =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36'
const SAFARI_IOS =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1'

describe('detectBrowserFromUserAgent — required families', () => {
  it('desktop Chrome', () => {
    expect(detectBrowserFromUserAgent(CHROME_DESKTOP)).toMatchObject({
      family: 'chrome',
      majorVersion: 140,
    })
  })

  it('desktop Edge (not Chrome)', () => {
    expect(detectBrowserFromUserAgent(EDGE_DESKTOP)).toMatchObject({
      family: 'edge',
      majorVersion: 140,
    })
  })

  it('desktop Firefox', () => {
    expect(detectBrowserFromUserAgent(FIREFOX_DESKTOP)).toMatchObject({
      family: 'firefox',
      majorVersion: 130,
    })
  })

  it('desktop Safari', () => {
    expect(detectBrowserFromUserAgent(SAFARI_DESKTOP)).toMatchObject({
      family: 'safari',
      majorVersion: 17,
    })
  })

  it('Android Chrome', () => {
    expect(detectBrowserFromUserAgent(CHROME_ANDROID)).toMatchObject({
      family: 'android_chrome',
      majorVersion: 140,
    })
  })

  it('iPhone Safari maps to ios_safari with the iOS OS version', () => {
    expect(detectBrowserFromUserAgent(SAFARI_IOS)).toMatchObject({
      family: 'ios_safari',
      majorVersion: 17,
    })
  })
})

describe('detectBrowserFromUserAgent — ambiguous / ordering cases', () => {
  it('Chrome on macOS is Chrome, never desktop Safari', () => {
    const ua =
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({ family: 'chrome', majorVersion: 140 })
  })

  it('Edge on macOS is Edge, never desktop Safari', () => {
    const ua =
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({ family: 'edge', majorVersion: 140 })
  })

  it('Edge on Android (EdgA) is Edge', () => {
    const ua =
      'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36 EdgA/140.0.0.0'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({ family: 'edge', majorVersion: 140 })
  })

  it('Chrome on iOS (CriOS) maps conservatively to ios_safari with the iOS OS version', () => {
    const ua =
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0.7151.0 Mobile/15E148 Safari/604.1'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({
      family: 'ios_safari',
      majorVersion: 17,
    })
  })

  it('Firefox on iOS (FxiOS) maps conservatively to ios_safari', () => {
    const ua =
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/130.0 Mobile/15E148 Safari/605.1.15'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({
      family: 'ios_safari',
      majorVersion: 17,
    })
  })

  it('iPad Safari maps to ios_safari', () => {
    const ua =
      'Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({
      family: 'ios_safari',
      majorVersion: 17,
    })
  })

  it('iOS device without a parseable OS version yields a null version', () => {
    const ua =
      'Mozilla/5.0 (iPhone; CPU iPhone OS like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({
      family: 'ios_safari',
      majorVersion: null,
    })
  })

  it('Samsung Internet is not classified as Chrome (fail closed as unknown)', () => {
    const ua =
      'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/120.0.0.0 Mobile Safari/537.36'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({ family: 'unknown', majorVersion: null })
  })

  it('Opera is not classified as Chrome (fail closed as unknown)', () => {
    const ua =
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 OPR/125.0.0.0'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({ family: 'unknown', majorVersion: null })
  })

  it('recognized family with unparseable version yields majorVersion null', () => {
    const ua =
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/ Safari/537.36'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({ family: 'chrome', majorVersion: null })
  })

  it('unknown legacy browser yields family unknown', () => {
    expect(detectBrowserFromUserAgent('Mozilla/5.0 (compatible; LegacyBrowser/1.0)')).toMatchObject(
      { family: 'unknown', majorVersion: null },
    )
  })

  it('Firefox on Android is not in the current policy families -> unknown (documented fail-closed)', () => {
    const ua = 'Mozilla/5.0 (Android 14; Mobile; rv:130.0) Gecko/130.0 Firefox/130.0'
    expect(detectBrowserFromUserAgent(ua)).toMatchObject({ family: 'unknown', majorVersion: null })
  })
})
