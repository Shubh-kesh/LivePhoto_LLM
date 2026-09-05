/**
 * Stub detector + factory tests (M3 §100-102, §117).
 */

import { describe, expect, it } from 'vitest'

import { createFaceDetectorProvider } from '../face/faceDetectorFactory'
import { StubFaceDetector, type StubFaceConfig } from '../face/StubFaceDetector'
import { MediaPipeFaceDetector } from '../face/MediaPipeFaceDetector'

function withStubMode(mode: StubFaceConfig['mode'], fn: () => Promise<void>) {
  const globalThisAny = globalThis as { __LIVEPHOTO_FACE_STUB__?: StubFaceConfig }
  const previous = globalThisAny.__LIVEPHOTO_FACE_STUB__
  globalThisAny.__LIVEPHOTO_FACE_STUB__ = { mode }
  return fn().finally(() => {
    if (previous === undefined) delete globalThisAny.__LIVEPHOTO_FACE_STUB__
    else globalThisAny.__LIVEPHOTO_FACE_STUB__ = previous
  })
}

describe('StubFaceDetector', () => {
  it('initializes to READY and reports concrete model versioning', async () => {
    const detector = new StubFaceDetector()
    expect(detector.state).toBe('NOT_INITIALIZED')
    await detector.initialize()
    expect(detector.state).toBe('READY')
    expect(detector.info.modelVersion).toBe('stub-v1')
    expect(detector.info.name).toBe('stub-face-detector')
  })

  it('returns one centered face by default', async () => {
    await withStubMode('good', async () => {
      const detector = new StubFaceDetector()
      await detector.initialize()
      const result = await detector.detect()
      expect(result.detections).toHaveLength(1)
      expect(result.detections[0].confidence).toBe(0.95)
      expect(result.detections[0].normalizedBoundingBox.width).toBeGreaterThan(0.3)
    })
  })

  it('returns no faces in noface mode', async () => {
    await withStubMode('noface', async () => {
      const detector = new StubFaceDetector()
      await detector.initialize()
      expect((await detector.detect()).detections).toHaveLength(0)
    })
  })

  it('returns two faces in multiple mode', async () => {
    await withStubMode('multiple', async () => {
      const detector = new StubFaceDetector()
      await detector.initialize()
      expect((await detector.detect()).detections).toHaveLength(2)
    })
  })

  it('dispose transitions to DISPOSED', async () => {
    const detector = new StubFaceDetector()
    await detector.initialize()
    detector.dispose()
    expect(detector.state).toBe('DISPOSED')
  })
})

describe('createFaceDetectorProvider', () => {
  it('returns the real MediaPipe provider by default (no stub build flag)', () => {
    expect(createFaceDetectorProvider()).toBeInstanceOf(MediaPipeFaceDetector)
  })
})
