import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

/**
 * M2/M3 browser E2E using Chromium with a synthetic (fake) camera (M2 §74-75, §89; M3 §100-102).
 *
 * - `--use-fake-ui-for-media-stream` auto-grants the camera permission prompt.
 * - `--use-file-for-fake-video-capture` streams a generated checkerboard .y4m (deterministic pixel
 *   metrics) instead of the browser's rolling pattern.
 * - `VITE_FACE_PROVIDER=stub` (webServer env) selects the deterministic stub face detector, which
 *   is controlled in-test via the in-memory `window.__LIVEPHOTO_FACE_STUB__` global. This is a
 *   test-build dependency seam — production builds never select the stub and no URL/local-storage
 *   flag can force QUALITY_READY.
 *
 * Passing Chromium E2E does NOT prove iOS Safari, Android hardware, or Windows camera-driver
 * compatibility — that requires physical-device validation (docs/CAMERA_COMPATIBILITY_MATRIX.md).
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
        // Resolve relative to the process cwd (Playwright transpiles the config, so import.meta.url
        // may point to a temp directory; the E2E runs with cwd = frontend/).
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
        // Deterministic portrait matting for E2E (no real model required in CI) + portrait on.
        PORTRAIT_PROCESSING_ENABLED: 'true',
        PORTRAIT_SEGMENTATION_PROVIDER: 'fake',
      },
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        VITE_FACE_PROVIDER: 'stub',
        // E2E always talks to the locally-provisioned backend (overrides any local frontend/.env).
        VITE_API_BASE_URL: 'http://localhost:8000',
      },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
})
