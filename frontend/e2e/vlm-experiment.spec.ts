/**
 * M4/M5.6 VLM experiment E2E — routed through the explicit development route /dev/vlm-experiment
 * (M5.5 §64-65, M5.6 §6). The customer /capture path never exposes the experiment unless the
 * runtime flag enables it. Uses the synthetic checkerboard camera, the stub face provider and the
 * real backend with the deterministic mock VLM provider. The test explicitly selects the mock
 * provider so no real Gemini/provider call can ever occur (M5.5 §99). No external API required.
 */

import { expect, test } from '@playwright/test'

const GOOD = { mode: 'good' }

async function reachPreview(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/dev/vlm-experiment')
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await page.getByRole('button', { name: 'Open camera' }).click()
  await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Capture photo' }).click()
  await expect(page.getByRole('button', { name: 'Use photo' })).toBeVisible({ timeout: 15_000 })
}

async function openPanel(page: import('@playwright/test').Page): Promise<void> {
  // The VLM panel is collapsed by default (M5.6 §6).
  await page.locator('.vlm-experiment__summary').click()
  await expect(page.getByText('Experimental result — not a banking decision.')).toBeVisible()
  // Always select the deterministic mock provider (no real provider call is allowed in E2E).
  await page.getByLabel('Provider').selectOption('mock')
}

test('quality-ready capture -> VLM experiment -> SCREEN_REPLAY result', async ({ page }) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)

  await reachPreview(page)
  await openPanel(page)

  await page.getByRole('button', { name: 'Run VLM test' }).click()

  const result = page.locator('.vlm-experiment__result')
  await expect(result).toContainText('SCREEN_REPLAY', { timeout: 15_000 })
  await expect(result).toContainText('mock-vision-v1')
  await expect(result).toContainText('DEVICE_BORDER_VISIBLE')
  await expect(result).toContainText('Request ID')
})

test('quality-ready capture -> VLM provider timeout -> safe error', async ({ page }) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)

  await reachPreview(page)
  await openPanel(page)

  // Mock behavior selector is test-build only (provider === 'mock').
  await page.getByLabel('Mock behavior (test builds)').selectOption('timeout')
  await page.getByRole('button', { name: 'Run VLM test' }).click()

  await expect(page.getByRole('alert')).toContainText('PROVIDER_TIMEOUT', { timeout: 20_000 })
  await expect(page.locator('.vlm-experiment__result')).not.toContainText('SCREEN_REPLAY')
})
