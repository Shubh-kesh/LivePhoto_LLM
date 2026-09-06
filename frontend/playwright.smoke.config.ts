import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

/**
 * Manual real-MediaPipe smoke config (M3 §95, M4 §2).
 *
 * - Loads the REAL MediaPipe face detector (no VITE_FACE_PROVIDER=stub) using the provisioned
 *   model + WASM (frontend/scripts/setup-face-assets.sh, pinned SHA-256).
 * - The spec itself skips unless the model asset is present AND LIVEPHOTO_RUN_REAL_MODEL_SMOKE=1.
 * - Never runs in ordinary CI.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: 'real-model-smoke.spec.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
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
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
