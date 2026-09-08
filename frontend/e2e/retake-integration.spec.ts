/**
 * M5.8.1 integrated Retake E2E: from Review, Retake must NOT upload/persist selected-original
 * (status stays RETRY_REQUIRED), the counted attempt is preserved, and the next Capture press gets
 * a new attempt id. Use photo then uploads the selected frame (count still at-most-once).
 */

import { expect, test } from '@playwright/test'

const DEV_AUTH = { 'X-LivePhoto-Dev-Auth': 'e2e-dev-secret' }

test('Retake from integrated Review does not commit selected-original and counts correctly', async ({
  page,
  request,
}) => {
  const externalId = `retake-${Date.now()}`
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
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByTestId('vlm-experiment')).toBeVisible({ timeout: 20_000 })

  // Retake: the counted attempt is preserved, but selected-original is NOT committed (no upload).
  await page.getByRole('button', { name: 'Retake photo' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })

  const afterRetake = await (
    await request.get(
      `http://localhost:5173/api/v1/integration/transactions/${externalId}/status?source=D365`,
      { headers: DEV_AUTH },
    )
  ).json()
  expect(afterRetake.attempt_count).toBe(1) // QUALITY_ELIGIBLE recorded, no upload added a count
  expect(afterRetake.status).toBe('RETRY_REQUIRED') // selected-original not persisted

  // Second capture -> a new attempt (count 2), then Use photo uploads (still 2, at-most-once).
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 20_000 })
  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('button', { name: 'Prepare portrait' })).toBeVisible({
    timeout: 20_000,
  })

  const final = await (
    await request.get(
      `http://localhost:5173/api/v1/integration/transactions/${externalId}/status?source=D365`,
      { headers: DEV_AUTH },
    )
  ).json()
  expect(final.attempt_count).toBe(2)
  expect(final.status).toBe('IN_PROGRESS') // capture committed (CAPTURE_READY)
})
