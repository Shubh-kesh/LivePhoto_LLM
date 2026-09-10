/**
 * Browser-policy E2E (pre-M6 minimum-version enforcement).
 *
 * Uses Playwright's user-agent override to represent a browser BELOW the configured minimum
 * (committed backend/config/browser-support.json: chrome minimum 120). The gate must hard-block
 * with "Browser update required", never mount the journey, never request the camera, and offer no
 * "Continue anyway". "Check again" re-probes fresh /info and stays blocked while below minimum.
 *
 * This exercises the policy path deterministically; it does NOT claim physical browser
 * compatibility (see docs/CAMERA_COMPATIBILITY_MATRIX.md). The UA override is a test seam only and
 * is never treated as a security boundary.
 */

import { expect, test, type Browser } from '@playwright/test'

const OLD_CHROME_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36'

async function openCaptureOnOldChrome(browser: Browser) {
  const context = await browser.newContext({ userAgent: OLD_CHROME_UA })
  const page = await context.newPage()
  await page.goto('/capture')
  return { context, page }
}

test('browser below the configured minimum is hard-blocked', async ({ browser }) => {
  const { context, page } = await openCaptureOnOldChrome(browser)
  try {
    await expect(page.getByRole('heading', { name: 'Browser update required' })).toBeVisible({
      timeout: 15_000,
    })
    await expect(
      page.getByText(
        'Your browser version is no longer supported. Please update your browser to continue.',
      ),
    ).toBeVisible()
    // The journey never mounts and no "Continue anyway" escape hatch exists.
    await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /continue anyway/i })).toHaveCount(0)
  } finally {
    await context.close()
  }
})

test('Check again re-probes fresh /info and stays blocked while below minimum', async ({
  browser,
}) => {
  const { context, page } = await openCaptureOnOldChrome(browser)
  try {
    await expect(page.getByRole('heading', { name: 'Browser update required' })).toBeVisible({
      timeout: 15_000,
    })
    await page.getByRole('button', { name: 'Check again' }).click()
    // Still below the minimum -> still blocked (Check again must NOT bypass the requirement).
    await expect(page.getByRole('heading', { name: 'Browser update required' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toHaveCount(0)
  } finally {
    await context.close()
  }
})
