import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

/**
 * E2E: same-origin topology via the Vite proxy. Fake camera + stub face/eye + fake portrait
 * segmentation + stub consumer callback.
 *
 * The authoritative liveness path uses the server-configured deterministic mock VLM provider
 * (VLM_PROVIDER=mock, VLM_MOCK_BEHAVIOR=live; only available in local/test/dev, never a
 * browser-supplied value). The backend webServer also enables S2S local-dev auth. No test-only
 * canonical PASS writer, no real VLM credentials, and no physical camera are used.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:5173',
  },
  webServer: [
    {
      command: 'uv run uvicorn app.main:app --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/health/live',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        VLM_EXPERIMENT_ENABLED: 'true',
        VLM_PROVIDER: 'mock',
        // Deterministic authoritative liveness for the happy-path E2Es (server-configured, never a
        // browser-supplied value; mock provider is only available in local/test/dev).
        VLM_MOCK_BEHAVIOR: 'live',
        VLM_TIMEOUT_SECONDS: '2',
        PORTRAIT_PROCESSING_ENABLED: 'true',
        PORTRAIT_SEGMENTATION_PROVIDER: 'fake',
        // M5.8: same-origin + local-dev S2S + E2E consumer fixture.
        PUBLIC_LIVEPHOTO_BASE_URL: 'http://localhost:5173',
        S2S_AUTH_MODE: 'local_dev',
        S2S_LOCAL_DEV_TOKEN: 'e2e-dev-secret',
        CONSUMER_PROFILES_PATH: 'config/consumers.e2e.json',
        FILE_STORAGE_ROOT: './local-data/e2e-file-storage',
      },
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        VITE_FACE_PROVIDER: 'stub',
        // Same-origin default (empty = relative); Vite proxies /api and /xbiz/live_photo/l.
        VITE_API_BASE_URL: '',
        // Standalone /capture diagnostic flow: enables the optional VLM diagnostics panel on the
        // raw Review. The integrated /xbiz route never shows it (autoProcess bypasses the raw
        // Review's diagnostics slot). /dev/vlm-experiment always shows the panel (dev build).
        VITE_VLM_EXPERIMENT_UI_ENABLED: 'true',
      },
    },
    {
      command: 'node e2e/stub-consumer.mjs',
      url: 'http://localhost:3001',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        permissions: ['camera'],
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
            `--use-file-for-fake-video-capture=${resolve(process.cwd(), 'e2e/.fixtures/camera.y4m')}`,
            '--no-sandbox',
          ],
        },
      },
    },
    {
      // Fake media streams are a Firefox preference (no file-based fake camera like Chromium);
      // camera permission is auto-granted via media.navigator.permission.disabled.
      name: 'firefox',
      use: {
        browserName: 'firefox',
        launchOptions: {
          firefoxUserPrefs: {
            'media.navigator.streams.fake': true,
            'media.navigator.permission.disabled': true,
          },
        },
      },
    },
    {
      // WebKit exposes no fake-camera seam in Playwright; camera-dependent specs are expected to
      // fail there. The connectivity-preflight spec is camera-free and runs in every engine.
      name: 'webkit',
      use: {
        browserName: 'webkit',
      },
    },
  ],
})
