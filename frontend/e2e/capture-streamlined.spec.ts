/**
 * Standalone /capture streamlined mode E2E: VITE_VLM_EXPERIMENT_UI_ENABLED=false bypasses the raw
 * review and auto-processes through backend-authoritative liveness (VLM_PROVIDER) to a
 * processed-portrait review (Retry / Use photo) that completes with the normal standalone success
 * screen. No VLM diagnostics, no "Retake photo" raw review.
 */

import { expect, test } from '@playwright/test'

test('standalone /capture streamlined: backend liveness -> processed-portrait review -> success', async ({
  page,
}) => {
  // Per-spec runtime config override (deterministic; this spec only).
  await page.route('**/runtime-config.js', (route) => {
    route.fulfill({
      body: 'window.__LIVEPHOTO_CONFIG__ = { appEnv: "", apiBaseUrl: "", vlmExperimentUiEnabled: false };',
      contentType: 'application/javascript',
    })
  })
  await page.addInitScript(() => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = {
      mode: 'good',
    }
  })

  await page.goto('/capture')
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeEnabled({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Capture photo' }).click()

  // Auto-processed portrait review: no raw "Retake photo", no VLM panel.
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('heading', { name: 'Your photo' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retake photo' })).toHaveCount(0)
  await expect(page.getByTestId('vlm-experiment')).toHaveCount(0)

  // Use photo completes the normal standalone flow -> success.
  await page.getByRole('button', { name: 'Use photo' }).click()
  await expect(page.getByRole('heading', { name: 'Photo captured successfully' })).toBeVisible()
})
