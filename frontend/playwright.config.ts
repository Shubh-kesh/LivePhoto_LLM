import { defineConfig } from '@playwright/test'

/**
 * M2 browser E2E using Chromium with a synthetic (fake) camera (M2 §74-75, §89).
 *
 * - `--use-fake-ui-for-media-stream` auto-grants the camera permission prompt.
 * - `--use-fake-device-for-media-stream` supplies a synthetic camera stream.
 * - No physical camera, no external network, no AI/bank/MSSQL dependencies.
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
        '--no-sandbox',
      ],
    },
  },
  webServer: {
    command: 'npm run dev',
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
