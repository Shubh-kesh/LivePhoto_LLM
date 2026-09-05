import { defineConfig } from '@playwright/test'
import { fileURLToPath } from 'node:url'

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
        `--use-file-for-fake-video-capture=${fileURLToPath(
          new URL('./e2e/.fixtures/camera.y4m', import.meta.url),
        )}`,
        '--no-sandbox',
      ],
    },
  },
  webServer: {
    command: 'VITE_FACE_PROVIDER=stub npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
})
