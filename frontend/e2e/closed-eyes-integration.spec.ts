/**
 * M5.8.1 integrated closed-eye E2E: with the eye stub closed, the shared pipeline routes to
 * QualityRetryScreen, registers QUALITY_RETRY (EYES_CLOSED) server-side, and never reaches Review
 * (so the VLM panel is not shown). After eyes-open, the capture proceeds normally. No callback.
 */

import { expect, test } from '@playwright/test'

const DEV_AUTH = { 'X-LivePhoto-Dev-Auth': 'e2e-dev-secret' }

test('closed eye on integrated route -> quality retry -> EYES_CLOSED -> no review/panel/callback', async ({
  page,
  request,
}) => {
  const externalId = `eye-${Date.now()}`
  await page.addInitScript(() => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = {
      mode: 'good',
    }
    ;(globalThis as { __LIVEPHOTO_EYE_STUB__?: unknown }).__LIVEPHOTO_EYE_STUB__ = {
      mode: 'closed',
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
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  // Closed eye -> local quality retry, Review never reached (no VLM panel).
  await expect(page.getByRole('heading', { name: "Let's try again" })).toBeVisible({
    timeout: 20_000,
  })
  await expect(page.getByTestId('vlm-experiment')).toHaveCount(0)

  // Server recorded QUALITY_RETRY / EYES_CLOSED exactly once; no completion (no callback).
  const statusRes = await request.get(
    `http://localhost:5173/api/v1/integration/transactions/${externalId}/status?source=D365`,
    { headers: DEV_AUTH },
  )
  expect(statusRes.status()).toBe(200)
  const status = await statusRes.json()
  expect(status.attempt_count).toBe(1)
  expect(status.reason_codes).toContain('EYES_CLOSED')
  expect(status.status).toBe('RETRY_REQUIRED')

  // Eyes open -> retry proceeds normally: quality-eligible auto-processes straight to the
  // processed-portrait review (no raw "Use photo" step).
  await page.evaluate(() => {
    ;(globalThis as { __LIVEPHOTO_EYE_STUB__?: unknown }).__LIVEPHOTO_EYE_STUB__ = {
      mode: 'open',
    }
  })
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Submit photo' })).toBeVisible({
    timeout: 60_000,
  })
})
