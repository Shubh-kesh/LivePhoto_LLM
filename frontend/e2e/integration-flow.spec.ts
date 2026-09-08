/**
 * M5.8 integration E2E (fake camera + stub face/eye + fake portrait segmentation + test-only PASS
 * writer + stub consumer). No real VLM credentials or physical camera.
 */

import { expect, test } from '@playwright/test'

const DEV_AUTH = { 'X-LivePhoto-Dev-Auth': 'e2e-dev-secret' }

async function launch(client: import('@playwright/test').APIRequestContext): Promise<string> {
  const res = await client.post('http://localhost:8000/api/v1/integration/launch-sessions', {
    headers: { ...DEV_AUTH, 'Content-Type': 'application/json' },
    data: { transaction_id: `e2e-${Date.now()}`, source: 'D365' },
  })
  expect(res.status()).toBe(200)
  return (await res.json()).launch_url
}

test('successful integration: launch -> clean URL -> capture -> portrait -> submit -> redirect', async ({
  page,
  request,
}) => {
  const launchUrl = await launch(request)
  await page.goto(launchUrl)

  // Redemption 302s to the clean URL; the token disappears from the address bar.
  await expect(page).toHaveURL(/\/xbiz\/live_photo\/?$/)
  await expect(page.getByRole('button', { name: 'Open camera' })).toBeVisible()

  await page.getByRole('button', { name: 'Open camera' }).click()
  // Capture stays disabled until the camera stream is attached.
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Prepare portrait' })).toBeVisible({
    timeout: 20_000,
  })
  await page.getByRole('button', { name: 'Prepare portrait' }).click()
  await expect(page.getByRole('button', { name: 'Submit photo' })).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: 'Submit photo' }).click()

  // Successful submit -> consumer redirect URL.
  await expect(page).toHaveURL(/localhost:3001\/complete/, { timeout: 30_000 })
})

test('invalid launch token shows link-unavailable', async ({ page }) => {
  await page.goto('http://localhost:5173/xbiz/live_photo/l/not-a-real-token-0000000000')
  await expect(page).toHaveURL(/\/xbiz\/live_photo\/?$/)
  await expect(page.getByRole('heading', { name: 'Link unavailable' })).toBeVisible()
})
