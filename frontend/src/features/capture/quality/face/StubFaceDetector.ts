/**
 * Deterministic stub face detector (M3 §100-102).
 *
 * Only compiled into builds explicitly configured with VITE_FACE_PROVIDER=stub (test/E2E builds).
 * It is NEVER active in production builds. Behavior is driven by an in-memory test global
 * (window.__LIVEPHOTO_FACE_STUB__) set by Playwright via addInitScript — not by URL parameters or
 * local storage, and no production path can force QUALITY_READY.
 */

import type { FaceDetectionResult, FaceDetectorInfo } from '../types/face'
import type { FaceDetectorProvider, FaceDetectorProviderState } from './FaceDetectorProvider'

export type StubFaceMode = 'good' | 'noface' | 'toosmall' | 'toolarge' | 'multiple'

export interface StubFaceConfig {
  mode?: StubFaceMode
}

const STUB_INFO: FaceDetectorInfo = {
  name: 'stub-face-detector',
  version: '1.0.0',
  modelVersion: 'stub-v1',
}

const IMAGE_WIDTH = 640
const IMAGE_HEIGHT = 480

function readStubMode(): StubFaceMode {
  const config = (globalThis as { __LIVEPHOTO_FACE_STUB__?: StubFaceConfig })
    .__LIVEPHOTO_FACE_STUB__
  return config?.mode ?? 'good'
}

function normalizedBox(x: number, y: number, width: number, height: number) {
  return {
    x,
    y,
    width,
    height,
    normalized: {
      x: x / IMAGE_WIDTH,
      y: y / IMAGE_HEIGHT,
      width: width / IMAGE_WIDTH,
      height: height / IMAGE_HEIGHT,
    },
  }
}

export class StubFaceDetector implements FaceDetectorProvider {
  readonly info: FaceDetectorInfo = STUB_INFO
  state: FaceDetectorProviderState = 'NOT_INITIALIZED'

  async initialize(): Promise<void> {
    this.state = 'READY'
  }

  async detect(): Promise<FaceDetectionResult> {
    const mode = readStubMode()
    const result: FaceDetectionResult = {
      detections: [],
      imageWidth: IMAGE_WIDTH,
      imageHeight: IMAGE_HEIGHT,
      inferenceTimeMs: 0,
    }

    if (mode === 'noface') return result
    if (mode === 'multiple') {
      result.detections.push(
        detectionFromBox(normalizedBox(60, 80, 200, 200), 0.9),
        detectionFromBox(normalizedBox(360, 120, 180, 180), 0.85),
      )
      return result
    }

    // Default: one centered, well-covered face.
    const box = normalizedBox(170, 100, 300, 300)
    if (mode === 'toosmall') {
      box.width = 40
      box.height = 40
    }
    if (mode === 'toolarge') {
      box.width = 560
      box.height = 480
    }
    result.detections.push(detectionFromBox(box, 0.95))
    return result
  }

  dispose(): void {
    this.state = 'DISPOSED'
  }
}

function detectionFromBox(box: ReturnType<typeof normalizedBox>, confidence: number) {
  return {
    confidence,
    boundingBox: { x: box.x, y: box.y, width: box.width, height: box.height },
    normalizedBoundingBox: box.normalized,
  }
}
