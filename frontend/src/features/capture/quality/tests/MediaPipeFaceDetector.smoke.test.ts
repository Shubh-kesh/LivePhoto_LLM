/**
 * Optional REAL-MODEL smoke test (M3 §95, §117).
 *
 * SKIPPED by default: it requires the face model + WASM to be provisioned locally via
 * `frontend/scripts/setup-face-assets.sh` (pinned SHA-256) and a real browser canvas. It is not
 * required for ordinary CI, contains no bank data, and never downloads the model.
 *
 * Run manually with:  npx vitest run src/features/capture/quality/tests/MediaPipeFaceDetector.smoke.test.ts
 */

import { describe, expect, it } from 'vitest'

import { MediaPipeFaceDetector } from '../face/MediaPipeFaceDetector'

describe.skip('MediaPipeFaceDetector real-model smoke (manual)', () => {
  it('initializes with the provisioned model and detects a synthetic face-like canvas', async () => {
    const detector = new MediaPipeFaceDetector()
    await detector.initialize()
    expect(detector.state).toBe('READY')
    expect(detector.info.modelVersion).not.toBe('latest')

    const canvas = document.createElement('canvas')
    canvas.width = 200
    canvas.height = 200
    const context = canvas.getContext('2d')
    if (!context) throw new Error('no 2d context')
    context.fillStyle = '#333'
    context.fillRect(0, 0, 200, 200)
    context.fillStyle = '#eee'
    context.beginPath()
    context.ellipse(100, 100, 40, 50, 0, 0, Math.PI * 2)
    context.fill()

    const result = await detector.detect(canvas)
    expect(result.detections.length).toBeGreaterThanOrEqual(1)
    detector.dispose()
    expect(detector.state).toBe('DISPOSED')
  }, 20_000)
})
