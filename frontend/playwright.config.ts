import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

/**
 * M5.8 E2E: same-origin topology via the Vite proxy. Fake camera + stub face/eye + fake portrait
 * segmentation + test-only canonical PASS writer + stub consumer callback.
 *
 * The backend webServer enables S2S local-dev auth and the test-only decision writer (never
 * available in UAT/production). No real VLM credentials or physical camera are used.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:5173',
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
        VLM_TIMEOUT_SECONDS: '2',
        PORTRAIT_PROCESSING_ENABLED: 'true',
        PORTRAIT_SEGMENTATION_PROVIDER: 'fake',
        // M5.8: same-origin + local-dev S2S + test-only decision writer + E2E consumer fixture.
        PUBLIC_LIVEPHOTO_BASE_URL: 'http://localhost:5173',
        S2S_AUTH_MODE: 'local_dev',
        S2S_LOCAL_DEV_TOKEN: 'e2e-dev-secret',
        CONSUMER_PROFILES_PATH: 'config/consumers.e2e.json',
        DECISION_TEST_WRITER_ENABLED: 'true',
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
        // Exercise the optional VLM diagnostics panel on the integrated Review (M5.8.1).
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
      use: { browserName: 'chromium' },
    },
  ],
})
