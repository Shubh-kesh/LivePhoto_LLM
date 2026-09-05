/**
 * Capture-flow E2E with a synthetic camera (M2 §74-75, §90; M3 §100-102).
 *
 * The synthetic stream and stub face detector are non-sensitive. CI does not collect screenshot
 * artifacts from this flow, so no real capture data can ever be uploaded from banking tests by
 * accident.
 *
 * The stub detector is selected via VITE_FACE_PROVIDER=stub (webServer env) and controlled through
 * the in-memory window.__LIVEPHOTO_FACE_STUB__ global set by addInitScript — never a production
 * URL/local-storage bypass.
 */

import { expect, test } from '@playwright/test'

const GOOD = { mode: 'good' }
const NO_FACE = { mode: 'noface' }

async function setStubMode(page: import('@playwright/test').Page, mode: string): Promise<void> {
  await page.evaluate((m) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = { mode: m }
  }, mode)
}

test('capture flow with a quality-ready face (Scenario 1)', async ({ page }) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)

  await page.goto('/capture')

  // Introduction is shown first; permission is requested only on explicit action.
  await expect(page.getByRole('heading', { name: /We need access to your camera/i })).toBeVisible()
  await page.getByRole('button', { name: 'Start camera' }).click()

  // Live preview stream attaches and quality guidance appears (Ready to capture).
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await expect
    .poll(() =>
      page.evaluate(() => {
        const el = document.querySelector('[data-testid="camera-video"]') as HTMLVideoElement | null
        return el ? Boolean(el.srcObject) : false
      }),
    )
    .toBe(true)

  // Capture burst -> quality analysis -> preview of the quality-selected frame.
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('img', { name: 'Your captured photo preview' })).toBeVisible()

  // Local performance observation (dev diagnostics; metrics only, never images).
  const diagnosticsText = await page
    .locator('.capture-diagnostics')
    .textContent()
    .catch(() => null)
  if (diagnosticsText) {
    console.log('LOCAL_PERF_DIAGNOSTICS:', diagnosticsText.replace(/\s+/g, ' ').trim())
  }

  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('heading', { name: 'Photo captured successfully.' })).toBeVisible()
})

test('capture flow with a quality retry, then success (Scenario 2)', async ({ page }) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, NO_FACE)

  await page.goto('/capture')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })

  // First capture: no face -> quality retry.
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('heading', { name: 'Photo needs to be retaken.' })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByRole('alert')).toContainText('face')

  // Switch to a good face, retake, capture again.
  await setStubMode(page, 'good')
  await page.getByRole('button', { name: 'Retake photo' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('heading', { name: 'Photo captured successfully.' })).toBeVisible()
})
