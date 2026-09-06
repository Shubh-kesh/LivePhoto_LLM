/**
 * M4 VLM experiment E2E (M4 §148). Uses the synthetic checkerboard camera, the stub face provider
 * and the real backend with the deterministic mock VLM provider. No external API required.
 */

import { expect, test } from '@playwright/test'

const GOOD = { mode: 'good' }

test('quality-ready capture -> VLM experiment -> SCREEN_REPLAY result', async ({ page }) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)

  await page.goto('/capture')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })

  // The experiment panel is available on the preview screen (development build).
  await expect(page.getByText('Experimental result — not a banking decision.')).toBeVisible()
  await page.getByRole('button', { name: 'Run VLM experiment' }).click()

  const result = page.locator('.vlm-experiment__result')
  await expect(result).toContainText('SCREEN_REPLAY', { timeout: 15_000 })
  await expect(result).toContainText('mock-vision-v1')
  await expect(result).toContainText('DEVICE_BORDER_VISIBLE')
})

test('quality-ready capture -> VLM provider timeout -> safe error', async ({ page }) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)

  await page.goto('/capture')
  await page.getByRole('button', { name: 'Start camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })

  await expect(page.getByText('Experimental result — not a banking decision.')).toBeVisible()
  // Mock behavior selector is test-build only (provider === 'mock').
  await page.getByLabel('Mock behavior (test builds)').selectOption('timeout')
  await page.getByRole('button', { name: 'Run VLM experiment' }).click()

  await expect(page.getByRole('alert')).toContainText('PROVIDER_TIMEOUT', { timeout: 20_000 })
  await expect(page.locator('.vlm-experiment__result')).not.toContainText('SCREEN_REPLAY')
})
