/**
 * M5.8 attempt E2E: frontend-only quality failure is registered server-side via /browser/attempts,
 * counts at most once per attempt_id, is exposed by the status API, and never triggers a callback.
 */

import { expect, test } from '@playwright/test'

const DEV_AUTH = { 'X-LivePhoto-Dev-Auth': 'e2e-dev-secret' }

test('frontend quality failure registers attempt, exposes reason, no callback', async ({
  page,
  context,
  request,
}) => {
  const externalTransactionId = `attempt-${Date.now()}`
  const res = await request.post('http://localhost:8000/api/v1/integration/launch-sessions', {
    headers: { ...DEV_AUTH, 'Content-Type': 'application/json' },
    data: {
      transaction_id: externalTransactionId,
      source: 'D365',
      ocr_required: false,
      camera_config: '1',
      white_background: true,
      output_file_format: 'jpeg',
    },
  })
  expect(res.status()).toBe(200)
  const launchUrl = (await res.json()).launch_url

  await page.goto(launchUrl)
  await expect(page).toHaveURL(/\/xbiz\/live_photo\/?$/)
  await expect(page.getByRole('button', { name: 'Open camera' })).toBeVisible()

  // The session-bound CSRF token is readable from the non-HttpOnly lp_csrf cookie.
  const csrf = await page.evaluate(() => {
    const m = document.cookie.match(/(?:^|;\s*)lp_csrf=([^;]+)/)
    return m ? decodeURIComponent(m[1]) : ''
  })
  expect(csrf).toBeTruthy()

  // Build the Cookie header from the browser context so the HttpOnly lp_session is attached.
  const cookies = await context.cookies('http://localhost:5173')
  const sessionCookie = cookies.find((c) => c.name === 'lp_session')
  expect(sessionCookie).toBeTruthy()
  const cookieHeader = `lp_session=${sessionCookie!.value}; lp_csrf=${csrf}`

  // Same attempt_id registered twice must increment the counter at most once. Calls go through the
  // same-origin proxy (localhost:5173) so the browser-session cookie + CSRF are honored.
  const attemptId = 'quality-fail-1'
  for (let i = 0; i < 2; i += 1) {
    const r = await request.post('http://localhost:5173/api/v1/browser/attempts', {
      headers: { 'X-CSRF-Token': csrf, Cookie: cookieHeader },
      form: { attempt_id: attemptId, result: 'QUALITY_RETRY', reason_code: 'EYES_CLOSED' },
    })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.attempt_count).toBe(1) // at most once
    expect(body.max_attempts).toBe(10)
  }

  // Status API exposes the allowlisted reason + count; no completion (no callback fired).
  const statusRes = await request.get(
    `http://localhost:5173/api/v1/integration/transactions/${externalTransactionId}/status?source=D365`,
    { headers: DEV_AUTH },
  )
  expect(statusRes.status()).toBe(200)
  const status = await statusRes.json()
  expect(status.reason_codes).toContain('EYES_CLOSED')
  expect(status.attempt_count).toBe(1)
  expect(status.status).toBe('RETRY_REQUIRED')
  expect(status.status).not.toBe('COMPLETED')
})
