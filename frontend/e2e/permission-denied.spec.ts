/**
 * Permission-denied E2E (M5.5 §34, §98). Deterministic: getUserMedia is stubbed (page init script,
 * test-only) to reject with a DOMException(name = 'NotAllowedError'), the same outcome a denied
 * browser prompt produces. Verifies the friendly blocked-camera UX and that no DOMException wording
 * is shown. This is the same test-seam approach as the stub face provider — never a production path.
 */

import { expect, test } from '@playwright/test'

test('camera permission denied -> friendly blocked message with Try again (no technical wording)', async ({
  page,
}) => {
  await page.addInitScript(() => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = {
      mode: 'good',
    }
    const md = navigator.mediaDevices as MediaDevices | undefined
    if (md) {
      Object.defineProperty(md, 'getUserMedia', {
        configurable: true,
        value: () => Promise.reject(new DOMException('Permission denied', 'NotAllowedError')),
      })
    }
  })

  await page.goto('/capture')
  await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
  await page.getByRole('button', { name: 'Open camera' }).click()

  await expect(page.getByRole('heading', { name: 'Camera access is blocked' })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByRole('alert')).toContainText('Allow camera permission')
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()

  const body = await page.locator('body').textContent()
  expect(body ?? '').not.toMatch(/NotAllowedError|DOMException|NotFoundError/i)
})
