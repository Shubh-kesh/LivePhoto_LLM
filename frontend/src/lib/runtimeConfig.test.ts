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
  it('falls back to safe defaults when no runtime config or Vite value is present', () => {
    setWindowConfig(undefined)
    const config = readRuntimeConfig({})
    expect(config.apiBaseUrl).toBe('') // same-origin relative base is the M5.8 default
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
    const config = readRuntimeConfig({})
    expect(config.appEnv).toBeTruthy()
    expect(config.apiBaseUrl).toBe('') // same-origin relative base
  })
})

describe('readRuntimeConfig VLM flag precedence (M5.6 correction)', () => {
  it('runtime empty + Vite true => true (local dev fallback)', () => {
    setWindowConfig({ vlmExperimentUiEnabled: '' })
    expect(
      readRuntimeConfig({ VITE_VLM_EXPERIMENT_UI_ENABLED: 'true' }).vlmExperimentUiEnabled,
    ).toBe(true)
  })

  it('runtime empty + Vite false => false', () => {
    setWindowConfig({ vlmExperimentUiEnabled: '' })
    expect(
      readRuntimeConfig({ VITE_VLM_EXPERIMENT_UI_ENABLED: 'false' }).vlmExperimentUiEnabled,
    ).toBe(false)
  })

  it('runtime true + Vite false => true (Docker UAT enabled wins)', () => {
    setWindowConfig({ vlmExperimentUiEnabled: true })
    expect(
      readRuntimeConfig({ VITE_VLM_EXPERIMENT_UI_ENABLED: 'false' }).vlmExperimentUiEnabled,
    ).toBe(true)
  })

  it('runtime false + Vite true => false (explicit Docker disable wins)', () => {
    setWindowConfig({ vlmExperimentUiEnabled: false })
    expect(
      readRuntimeConfig({ VITE_VLM_EXPERIMENT_UI_ENABLED: 'true' }).vlmExperimentUiEnabled,
    ).toBe(false)
  })
})
