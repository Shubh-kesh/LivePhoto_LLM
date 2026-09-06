/**
 * Public runtime configuration loaded before the app module (M5.6 §3-5).
 *
 * In Docker the nginx entrypoint overwrites this file from LIVEPHOTO_* environment variables at
 * container start (no rebuild needed). In local Vite development this committed default has empty
 * values, so the app falls back to VITE_* compile-time variables. Never place secrets here.
 */
window.__LIVEPHOTO_CONFIG__ = {
  appEnv: '',
  apiBaseUrl: '',
  vlmExperimentUiEnabled: false,
}
