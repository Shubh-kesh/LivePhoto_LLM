/**
 * Closed-eye capture-gate E2E (M5.7 §34, §16-18).
 *
 * Uses the stub face provider + stub eye-state evaluator (VITE_FACE_PROVIDER=stub). A closed-eye
 * capture can never produce a final frame: the customer gets the eyes-open guidance/retry, and
 * only an eyes-open burst produces a usable preview + success. No real face or camera is used.
 */

import { expect, test } from '@playwright/test'

const GOOD = { mode: 'good' }

async function setEyeMode(page: import('@playwright/test').Page, mode: string): Promise<void> {
  await page.evaluate((m) => {
    ;(globalThis as { __LIVEPHOTO_EYE_STUB__?: unknown }).__LIVEPHOTO_EYE_STUB__ = { mode: m }
  }, mode)
}

test('closed eyes -> eyes-open guidance and retry; open eyes -> capture succeeds', async ({
  page,
}) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
    ;(globalThis as { __LIVEPHOTO_EYE_STUB__?: unknown }).__LIVEPHOTO_EYE_STUB__ = {
      mode: 'closed',
    }
  }, GOOD)

  await page.goto('/capture')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })

  // Live guidance tells the customer to open their eyes (customer-safe, no raw codes).
  await expect
    .poll(
      () =>
        page
          .getByRole('status')
          .first()
          .textContent()
          .catch(() => ''),
      { timeout: 15_000 },
    )
    .toContain('Open your eyes and look at the camera')

  // A closed-eye capture cannot produce a final frame: quality retry with customer copy.
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('heading', { name: "Let's try again" })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByRole('alert')).toContainText('Keep your eyes open and look at the camera.')
  await expect(page.getByRole('alert')).not.toContainText('EYES_CLOSED')
  await expect(page.getByRole('button', { name: 'Use photo' })).not.toBeVisible()

  // Customer opens their eyes; retry succeeds and produces the final photo.
  await setEyeMode(page, 'open')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('heading', { name: 'Photo captured successfully' })).toBeVisible()
})
