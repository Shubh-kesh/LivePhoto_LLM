/**
 * Pre-M6 UX integrated E2E: the /xbiz/live_photo route uses the real capture pipeline and, on
 * quality-eligible, AUTOMATICALLY uploads the selected frame and prepares the processed portrait.
 * The customer reviews the PROCESSED PORTRAIT (Retry / Submit photo). No raw Review ("Use photo"),
 * no "Prepare portrait" button, and no VLM diagnostics on the customer flow. Submit -> callback ->
 * redirect. attempt_count stays 1 (at-most-once).
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

test('integrated journey: capture -> auto upload -> auto portrait -> processed-portrait review -> submit -> redirect', async ({
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

  await expect(page).toHaveURL(/\/xbiz\/live_photo\/?$/)

  // Shared pipeline: permission stage (explicit Open camera action).
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  // Automatic flow: upload + portrait. The processed-portrait review appears directly.
  await expect(page.getByRole('button', { name: 'Submit photo' })).toBeVisible({
    timeout: 60_000,
  })
  await expect(page.getByRole('heading', { name: 'Your photo' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()

  // No raw Review, no Prepare portrait, no VLM diagnostics on the customer flow.
  await expect(page.getByRole('button', { name: 'Use photo' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Prepare portrait' })).toHaveCount(0)
  await expect(page.getByTestId('vlm-experiment')).toHaveCount(0)

  // Submit -> consumer redirect.
  await page.getByRole('button', { name: 'Submit photo' }).click()
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
