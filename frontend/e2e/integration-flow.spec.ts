/**
 * M5.8.1 integrated E2E: the /xbiz/live_photo route uses the SAME real capture pipeline as /capture
 * (fake camera + stub face/eye + fake portrait segmentation + test-only PASS writer + stub
 * consumer). Verifies: launch -> clean URL -> permission -> burst capture -> quality eligible ->
 * Review -> VLM panel visible and stable -> Use photo (selected frame upload) -> portrait -> Submit
 * -> callback -> redirect; attempt_count stays 1 (at-most-once).
 */

import { expect, test } from '@playwright/test'

const DEV_AUTH = { 'X-LivePhoto-Dev-Auth': 'e2e-dev-secret' }

async function launch(client: import('@playwright/test').APIRequestContext): Promise<{
  url: string
  externalId: string
}> {
  const externalId = `e2e-${Date.now()}`
  const res = await client.post('http://localhost:8000/api/v1/integration/launch-sessions', {
    headers: { ...DEV_AUTH, 'Content-Type': 'application/json' },
    data: {
      transaction_id: externalId,
      source: 'D365',
      ocr_required: false,
      camera_config: '1',
      white_background: true,
      output_file_format: 'jpeg',
    },
  })
  expect(res.status()).toBe(200)
  return { url: (await res.json()).launch_url, externalId }
}

test('integrated happy path: shared burst/quality pipeline -> VLM panel -> submit -> redirect', async ({
  page,
  request,
}) => {
  await page.addInitScript(() => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = {
      mode: 'good',
    }
  })
  const { url, externalId } = await launch(request)
  await page.goto(url)

  // Redemption 302s to the clean URL; the token disappears from the address bar.
  await expect(page).toHaveURL(/\/xbiz\/live_photo\/?$/)

  // Shared pipeline: permission stage (explicit Open camera action).
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  // Quality eligible -> Review with the real selected frame.
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 20_000 })

  // VLM panel is visible on the integrated Review and stays mounted.
  const panel = page.getByTestId('vlm-experiment')
  await expect(panel).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(500)
  await expect(panel).toBeVisible()

  // Use photo -> uploads the selected frame (same attempt_id; count stays 1).
  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('button', { name: 'Prepare portrait' })).toBeVisible({
    timeout: 20_000,
  })
  await page.getByRole('button', { name: 'Prepare portrait' }).click()
  await expect(page.getByRole('button', { name: 'Submit photo' })).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: 'Submit photo' }).click()

  // Successful submit -> consumer redirect.
  await expect(page).toHaveURL(/localhost:3001\/complete/, { timeout: 30_000 })

  // At-most-once counting and completion via the status API.
  const statusRes = await request.get(
    `http://localhost:5173/api/v1/integration/transactions/${externalId}/status?source=D365`,
    { headers: DEV_AUTH },
  )
  expect(statusRes.status()).toBe(200)
  const status = await statusRes.json()
  expect(status.status).toBe('COMPLETED')
  expect(status.attempt_count).toBe(1)
})

test('invalid launch token shows link-unavailable', async ({ page }) => {
  await page.goto('http://localhost:5173/xbiz/live_photo/l/not-a-real-token-0000000000')
  await expect(page).toHaveURL(/\/xbiz\/live_photo\/?$/)
  await expect(page.getByRole('heading', { name: 'Link unavailable' })).toBeVisible()
})
