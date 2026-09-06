/**
 * Mobile capture-button regression (M5.6 §37-44, §87).
 *
 * Real user-reported issue: on a phone the Capture button could require scrolling to reach. This
 * test asserts, WITHOUT scrolling first, that the Capture photo button's bounding box lies fully
 * inside the viewport and that the active camera state has no horizontal/vertical scroll, across
 * the target small mobile viewport sizes.
 */

import { expect, test } from '@playwright/test'

const GOOD = { mode: 'good' }

const MOBILE_SIZES: ReadonlyArray<readonly [number, number]> = [
  [360, 640],
  [375, 667],
  [360, 800],
  [390, 844],
  [430, 932],
]

test('capture button is fully visible without scrolling on small mobile viewports', async ({
  page,
}) => {
  await page.addInitScript((config) => {
    ;(globalThis as { __LIVEPHOTO_FACE_STUB__?: unknown }).__LIVEPHOTO_FACE_STUB__ = config
  }, GOOD)

  for (const [width, height] of MOBILE_SIZES) {
    await page.setViewportSize({ width, height })
    await page.goto('/capture')
    await expect(page.getByRole('heading', { name: 'Prepare for your photo' })).toBeVisible()
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByRole('heading', { name: 'Camera access' })).toBeVisible()
    await page.getByRole('button', { name: 'Open camera' }).click()
    await expect(page.getByRole('button', { name: 'Capture photo' })).toBeVisible({
      timeout: 15_000,
    })

    // No programmatic scrolling before this assertion.
    const metrics = await page.evaluate(() => {
      const button = Array.from(document.querySelectorAll('button')).find(
        (el) => el.getAttribute('aria-label') === 'Capture photo',
      )
      const rect = button?.getBoundingClientRect()
      const scroller = document.scrollingElement
      return {
        top: rect?.top ?? -1,
        bottom: rect?.bottom ?? -1,
        left: rect?.left ?? -1,
        right: rect?.right ?? -1,
        vw: window.innerWidth,
        vh: window.innerHeight,
        scrollW: scroller?.scrollWidth ?? 0,
        clientW: scroller?.clientWidth ?? 0,
        scrollH: scroller?.scrollHeight ?? 0,
        clientH: scroller?.clientHeight ?? 0,
      }
    })

    expect(metrics.top, `top inside viewport @ ${width}x${height}`).toBeGreaterThanOrEqual(0)
    expect(metrics.bottom, `bottom inside viewport @ ${width}x${height}`).toBeLessThanOrEqual(
      metrics.vh,
    )
    expect(metrics.left, `left inside viewport @ ${width}x${height}`).toBeGreaterThanOrEqual(0)
    expect(metrics.right, `right inside viewport @ ${width}x${height}`).toBeLessThanOrEqual(
      metrics.vw,
    )
    // No horizontal scroll; no vertical scroll required for the primary controls.
    expect(metrics.scrollW, `no horizontal overflow @ ${width}x${height}`).toBeLessThanOrEqual(
      metrics.clientW,
    )
    expect(metrics.scrollH, `no vertical overflow @ ${width}x${height}`).toBeLessThanOrEqual(
      metrics.clientH + 1,
    )

    console.log(
      `MOBILE_OK ${width}x${height} buttonBottom=${metrics.bottom} vh=${metrics.vh} scrollH=${metrics.scrollH}`,
    )
  }
})
