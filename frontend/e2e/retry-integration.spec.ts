/**
 * Pre-M6 UX integrated Retry E2E: from the processed-portrait review, Retry returns to the camera
 * journey. The next physical Capture press mints a NEW attempt id and the automatic upload/portrait
 * runs again (attempt_count reflects both captures). The previous portrait is never submitted.
 */

import { expect, test } from '@playwright/test'

const DEV_AUTH = { 'X-LivePhoto-Dev-Auth': 'e2e-dev-secret' }

test('Retry from processed-portrait review returns to capture; next capture mints a new attempt', async ({
  page,
  request,
}) => {
  const externalId = `retry-${Date.now()}`
  await page.addInitScript(() => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = {
      mode: 'good',
    }
  })
  const res = await request.post('http://localhost:8000/api/v1/integration/launch-sessions', {
    headers: { ...DEV_AUTH, 'Content-Type': 'application/json' },
    data: { transaction_id: externalId, source: 'D365' },
  })
  expect(res.status()).toBe(200)
  const launchUrl = (await res.json()).launch_url

  await page.goto(launchUrl)
  await expect(page).toHaveURL(/\/xbiz\/live_photo\/?$/)
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  // First automatic capture -> processed-portrait review.
  await expect(page.getByRole('button', { name: 'Submit photo' })).toBeVisible({
    timeout: 60_000,
  })
  expect(
    (
      await (
        await request.get(
          `http://localhost:5173/api/v1/integration/transactions/${externalId}/status?source=D365`,
          { headers: DEV_AUTH },
        )
      ).json()
    ).attempt_count,
  ).toBe(1)

  // Retry -> back to the camera journey (permission stage).
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  // Second automatic capture -> processed-portrait review; attempt_count is now 2.
  await expect(page.getByRole('button', { name: 'Submit photo' })).toBeVisible({
    timeout: 60_000,
  })
  const final = await (
    await request.get(
      `http://localhost:5173/api/v1/integration/transactions/${externalId}/status?source=D365`,
      { headers: DEV_AUTH },
    )
  ).json()
  expect(final.attempt_count).toBe(2)
})
