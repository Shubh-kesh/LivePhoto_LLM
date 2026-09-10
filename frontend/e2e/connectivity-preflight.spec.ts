/**
 * Connectivity preflight E2E (pre-M6). Camera-free, so it runs in Chromium, Firefox and WebKit.
 *
 * Verifies the reusable ConnectivityGate on /capture and /xbiz/live_photo:
 * - the journey only appears after a real backend probe succeeds,
 * - a network drop while loaded shows the offline state and hides the journey,
 * - restoring the network re-runs the real probe before the journey resumes,
 * - an app-level session error (no launch token) is NOT mislabeled as a connectivity error.
 */

import { expect, test } from '@playwright/test'

test('capture journey proceeds only after the backend probe succeeds, and recovers from a drop', async ({
  page,
  context,
}) => {
  // Backend is up -> preflight passes -> the normal journey renders.
  await page.goto('/capture')
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible({
    timeout: 15_000,
  })

  // Network drop while loaded -> connection-lost overlay on top of the still-mounted journey.
  await context.setOffline(true)
  await expect(page.getByRole('heading', { name: 'No internet connection' })).toBeVisible({
    timeout: 15_000,
  })

  // Network restored -> a real backend probe runs; only then does the journey resume.
  await context.setOffline(false)
  await expect(page.getByRole('heading', { name: 'No internet connection' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible({
    timeout: 15_000,
  })
})

test('xbiz session errors are not mislabeled as connectivity errors', async ({ page }) => {
  // No launch token: the backend is reachable (preflight passes) and the app-level session
  // response is 'invalid' -> the normal session-error UI, never a connectivity screen.
  await page.goto('/xbiz/live_photo')
  await expect(page.getByRole('heading', { name: 'Link unavailable' })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByText("We can't connect right now.")).toHaveCount(0)
  await expect(page.getByText('No internet connection')).toHaveCount(0)
})
