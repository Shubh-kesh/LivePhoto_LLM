/**
 * Polished capture-flow E2E with a synthetic camera — M5.5 customer journey (M5.5 §96-99).
 *
 * The journey: /capture -> preparation -> Continue -> permission explanation -> Open camera ->
 * streaming -> capture -> quality -> preview -> Use photo -> capture-success.
 *
 * The synthetic stream and stub face detector are non-sensitive. CI does not collect screenshot
 * artifacts from this flow, so no real capture data can ever be uploaded from banking tests by
 * accident. The stub detector is selected via VITE_FACE_PROVIDER=stub (webServer env) and
 * controlled through the in-memory window.__LIVEPHOTO_FACE_STUB__ global — never a production
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

async function goToCamera(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/capture')
  // Preparation first on a fresh visit; camera is never requested automatically.
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
}

test('polished journey: preparation -> permission -> camera -> capture -> preview -> success', async ({
  page,
}) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)

  await page.goto('/capture')

  // Preparation first on every fresh visit; camera is not opened automatically.
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible()
  await expect(page.getByText('Remove your mask')).toBeVisible()
  await expect(page.getByText('Remove spectacles')).toBeVisible()
  await expect(page.getByText('Find a well-lit place')).toBeVisible()

  // Continue -> permission explanation.
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await expect(page.getByText('Your microphone will not be used.')).toBeVisible()

  // Open camera -> synthetic stream attaches -> guidance appears.
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await expect
    .poll(() =>
      page.evaluate(() => {
        const el = document.querySelector('[data-testid="camera-video"]') as HTMLVideoElement | null
        return el ? Boolean(el.srcObject) : false
      }),
    )
    .toBe(true)
  await expect(page.getByRole('status').filter({ hasText: 'Ready to capture' })).toBeVisible({
    timeout: 15_000,
  })

  // Capture -> quality analysis -> preview of the quality-selected frame.
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('img', { name: 'Your captured photo preview' })).toBeVisible()

  await page.getByRole('button', { name: 'Use photo' }).click()
  // Capture-success wording only — never liveness/verification.
  await expect(page.getByRole('heading', { name: 'Photo captured successfully' })).toBeVisible()
  await expect(page.getByText('Your photo is ready.')).toBeVisible()
  await expect(page.getByText(/verified|liveness|identity verified|passed/i)).toHaveCount(0)
})

test('quality retry, then success (Scenario 2)', async ({ page }) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, NO_FACE)

  await goToCamera(page)

  // First capture: no face -> quality retry with customer copy.
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('heading', { name: "Let's try again" })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByRole('alert')).toContainText("We couldn't see your face clearly.")
  await expect(page.getByRole('alert')).not.toContainText('NO_FACE')

  // Switch to a good face, try again, capture again.
  await setStubMode(page, 'good')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('heading', { name: 'Photo captured successfully' })).toBeVisible()
})
