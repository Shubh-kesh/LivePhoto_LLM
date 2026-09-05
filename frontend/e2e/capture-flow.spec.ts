/**
 * Capture-flow E2E with a synthetic camera (M2 §74-75, §90).
 *
 * The synthetic stream is non-sensitive; still, CI does not collect screenshot artifacts from
 * this flow, so no real capture data can ever be uploaded from banking tests by accident.
 */

import { expect, test } from '@playwright/test'

test('capture flow with a fake camera', async ({ page }) => {
  await page.goto('/capture')

  // Introduction is shown first; permission is requested only on explicit action.
  await expect(page.getByRole('heading', { name: /We need access to your camera/i })).toBeVisible()
  await page.getByRole('button', { name: 'Start camera' }).click()

  // Live preview stream attaches.
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  const video = page.getByTestId('camera-video')
  await expect(video).toBeVisible()
  await expect
    .poll(() =>
      page.evaluate(() => {
        const el = document.querySelector('[data-testid="camera-video"]') as HTMLVideoElement | null
        return el ? Boolean(el.srcObject) : false
      }),
    )
    .toBe(true)

  // Capture burst -> preview.
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('img', { name: 'Your captured photo preview' })).toBeVisible()

  // Retake reacquires the camera, then capture again.
  await page.getByRole('button', { name: 'Retake photo' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })

  // Confirm — acquisition-only wording; no liveness claim.
  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('heading', { name: 'Photo captured successfully.' })).toBeVisible()
})
