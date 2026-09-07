/**
 * Review-screen VLM placement E2E (M5.6 correction §12-15, §14-15).
 *
 * Regression for the reported bug: the VLM control was rendered AFTER the full-viewport Review
 * screen (.lp-screen min-height:100dvh), so it started below the fold. The fix renders the VLM
 * panel INSIDE the Review content. Unlike the active camera screen, Review MAY scroll normally.
 */

import { expect, test } from '@playwright/test'

const GOOD = { mode: 'good' }

async function reachReview(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/dev/vlm-experiment')
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
}

async function setupStub(page: import('@playwright/test').Page): Promise<void> {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)
}

const MOBILE_SIZES: ReadonlyArray<readonly [number, number]> = [
  [360, 640],
  [390, 844],
]

test('mobile Review: actions visible and VLM test reachable by ordinary scrolling', async ({
  page,
}) => {
  await setupStub(page)
  for (const [width, height] of MOBILE_SIZES) {
    await page.setViewportSize({ width, height })
    await reachReview(page)

    // Review actions are visible without any scrolling.
    await expect(page.getByRole('button', { name: 'Retake photo' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible()

    // The VLM control lives inside the Review screen content.
    const insideReview = await page.evaluate(() =>
      Boolean(document.querySelector('.lp-screen .vlm-experiment')),
    )
    expect(insideReview, `VLM inside Review content @ ${width}x${height}`).toBe(true)

    // Reachable with ordinary page scrolling (Review MAY scroll — no fixed/no-scroll here).
    await page.locator('.vlm-experiment__summary').scrollIntoViewIfNeeded()
    await expect(page.locator('.vlm-experiment__summary')).toBeVisible()
    await page.locator('.vlm-experiment__summary').click()
    await expect(page.getByText('Experimental result — not a banking decision.')).toBeVisible()
  }
})

test('desktop Review: VLM test appears naturally below the actions and stays contained', async ({
  page,
}) => {
  await setupStub(page)
  await page.setViewportSize({ width: 1366, height: 768 })
  await reachReview(page)

  await expect(page.getByRole('button', { name: 'Retake photo' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible()

  const insideReview = await page.evaluate(() =>
    Boolean(document.querySelector('.lp-screen .vlm-experiment')),
  )
  expect(insideReview).toBe(true)

  await page.locator('.vlm-experiment__summary').scrollIntoViewIfNeeded()
  await expect(page.locator('.vlm-experiment__summary')).toBeVisible()
  await page.locator('.vlm-experiment__summary').click()
  await expect(page.getByText('Experimental result — not a banking decision.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run VLM test' })).toBeVisible()
})
