/**
 * REAL MediaPipe face-detector smoke test (M3 §95, M4 §2).
 *
 * Manual-only: skips unless the provisioned model asset is present
 * (frontend/scripts/setup-face-assets.sh, pinned SHA-256) and LIVEPHOTO_RUN_REAL_MODEL_SMOKE=1.
 * Uses a synthetic checkerboard camera (no face) — this proves model + WASM initialization and
 * that detection runs, NOT that liveness/spoof detection works (M4 §150).
 *
 * Run:
 *   LIVEPHOTO_RUN_REAL_MODEL_SMOKE=1 npx playwright test -c playwright.smoke.config.ts
 */

import { expect, test } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const modelPath = fileURLToPath(new URL('../model-assets/face_detector.task', import.meta.url))
const modelPresent = existsSync(modelPath)
const runEnabled = process.env.LIVEPHOTO_RUN_REAL_MODEL_SMOKE === '1'

test('real MediaPipe model initializes and detects on a synthetic frame', async ({ page }) => {
  test.skip(!runEnabled, 'LIVEPHOTO_RUN_REAL_MODEL_SMOKE not enabled')
  test.skip(!modelPresent, 'face model asset not provisioned (run scripts/setup-face-assets.sh)')

  const manifest = JSON.parse(
    readFileSync(fileURLToPath(new URL('../model-assets/manifest.json', import.meta.url)), 'utf8'),
  )
  console.log('REAL_MODEL_MANIFEST:', JSON.stringify(manifest.model))

  await page.goto('/capture')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('button', { name: 'Open camera' }).click()

  // Detector initializes (model + WASM load from the LivePhoto origin). If initialization fails,
  // the UI shows "Quality check is unavailable." Instead, live guidance (NO_FACE on the synthetic
  // checkerboard) proves the real detector ran successfully.
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 30_000 })
  await expect
    .poll(
      () =>
        page
          .getByRole('status')
          .first()
          .textContent()
          .catch(() => ''),
      { timeout: 30_000 },
    )
    .not.toContain('Quality check is unavailable')

  const guidance = await page
    .getByRole('status')
    .first()
    .textContent()
    .catch(() => '')
  console.log('REAL_MODEL_GUIDANCE:', guidance)

  // Capture -> quality analysis with the real detector -> quality retry (no face in synthetic
  // checkerboard) -> bundle analysis time = real inference latency evidence.
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('heading', { name: "Let's try again" })).toBeVisible({
    timeout: 30_000,
  })
  console.log('REAL_MODEL_DIAGNOSTICS: (dev diagnostics removed from the customer path)')
})
