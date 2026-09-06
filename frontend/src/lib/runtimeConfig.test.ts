/**
 * Runtime-config tests (M5.6 §5, §83): runtime `window.__LIVEPHOTO_CONFIG__` takes precedence,
 * and the app falls back to Vite compile-time vars when the runtime config is absent/empty.
 */

import { afterEach, describe, expect, it } from 'vitest'

import { readRuntimeConfig } from './runtimeConfig'

const ORIGINAL = { ...window.__LIVEPHOTO_CONFIG__ }

function setWindowConfig(value: Record<string, unknown> | undefined): void {
  if (value === undefined) {
    delete (window as { __LIVEPHOTO_CONFIG__?: Record<string, unknown> }).__LIVEPHOTO_CONFIG__
  } else {
    ;(window as { __LIVEPHOTO_CONFIG__?: Record<string, unknown> }).__LIVEPHOTO_CONFIG__ = value
  }
}

afterEach(() => {
  if (ORIGINAL === undefined) {
    delete (window as { __LIVEPHOTO_CONFIG__?: Record<string, unknown> }).__LIVEPHOTO_CONFIG__
  } else {
    ;(window as { __LIVEPHOTO_CONFIG__?: Record<string, unknown> }).__LIVEPHOTO_CONFIG__ = ORIGINAL
  }
})

describe('readRuntimeConfig', () => {
  it('falls back to defaults when no runtime config is present', () => {
    setWindowConfig(undefined)
    const config = readRuntimeConfig()
    expect(config.apiBaseUrl).toBeTruthy()
    expect(config.appEnv).toBeTruthy()
    expect(config.vlmExperimentUiEnabled).toBe(false)
  })

  it('runtime config takes precedence over Vite defaults', () => {
    setWindowConfig({
      appEnv: 'uat',
      apiBaseUrl: 'https://api.example.internal',
      vlmExperimentUiEnabled: true,
    })
    const config = readRuntimeConfig()
    expect(config.appEnv).toBe('uat')
    expect(config.apiBaseUrl).toBe('https://api.example.internal')
    expect(config.vlmExperimentUiEnabled).toBe(true)
  })

  it('parses boolean flags as strings from runtime env', () => {
    setWindowConfig({ vlmExperimentUiEnabled: 'true' })
    expect(readRuntimeConfig().vlmExperimentUiEnabled).toBe(true)
    setWindowConfig({ vlmExperimentUiEnabled: 'false' })
    expect(readRuntimeConfig().vlmExperimentUiEnabled).toBe(false)
  })

  it('empty runtime strings fall back to defaults', () => {
    setWindowConfig({ appEnv: '', apiBaseUrl: '', vlmExperimentUiEnabled: false })
    const config = readRuntimeConfig()
    expect(config.appEnv).toBeTruthy()
    expect(config.apiBaseUrl).toBeTruthy()
  })
})
