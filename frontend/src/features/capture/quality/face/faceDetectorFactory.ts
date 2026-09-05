/**
 * FaceDetectorProvider factory (M3 §9, §100-102).
 *
 * Selects the stub provider only when the build is explicitly compiled with VITE_FACE_PROVIDER=stub
 * (test/E2E builds). Production builds always use the real MediaPipe provider. This is a build-time
 * dependency seam, not a runtime bypass.
 */

import type { FaceDetectorProvider } from './FaceDetectorProvider'
import { MediaPipeFaceDetector } from './MediaPipeFaceDetector'
import { StubFaceDetector } from './StubFaceDetector'

export function createFaceDetectorProvider(): FaceDetectorProvider {
  if (import.meta.env.VITE_FACE_PROVIDER === 'stub') {
    return new StubFaceDetector()
  }
  return new MediaPipeFaceDetector()
}
