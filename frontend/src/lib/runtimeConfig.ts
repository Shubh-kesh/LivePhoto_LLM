/**
 * Runtime configuration (M5.6 §3-5, §53, §74-75, §83).
 *
 * Reads ``window.__LIVEPHOTO_CONFIG__`` (set synchronously by ``/runtime-config.js`` before the app
 * module runs). Runtime values take precedence when present; otherwise the app falls back to Vite
 * compile-time ``VITE_*`` variables for local development. Tests cover this fallback.
 *
 * Only non-sensitive public settings are exposed. Never place API keys, database strings, Gemma
 * secrets or internal credentials here.
 */

export interface RuntimeConfig {
  appEnv: string
  apiBaseUrl: string
  vlmExperimentUiEnabled: boolean
}

declare global {
  interface Window {
    __LIVEPHOTO_CONFIG__?: Record<string, unknown>
  }
}

function boolValue(value: unknown, fallback: boolean): boolean {
  if (value === true || value === 'true' || value === '1') return true
  if (value === false || value === 'false' || value === '0') return false
  return fallback
}

function strValue(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

export function readRuntimeConfig(env: Record<string, unknown> = import.meta.env): RuntimeConfig {
  const cfg = (typeof window !== 'undefined' ? window.__LIVEPHOTO_CONFIG__ : undefined) ?? {}
  const apiBaseUrl = strValue(
    cfg.apiBaseUrl,
    strValue(env.VITE_API_BASE_URL, 'http://localhost:8000'),
  )
  const appEnv = strValue(cfg.appEnv, strValue(env.VITE_APP_ENV, 'development'))
  const vlmExperimentUiEnabled = boolValue(
    cfg.vlmExperimentUiEnabled,
    boolValue(env.VITE_VLM_EXPERIMENT_UI_ENABLED, false),
  )
  return { appEnv, apiBaseUrl, vlmExperimentUiEnabled }
}

export const runtimeConfig: RuntimeConfig = readRuntimeConfig()
