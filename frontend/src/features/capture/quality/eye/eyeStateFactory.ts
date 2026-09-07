/**
 * EyeStateEvaluatorProvider factory (M5.7 §19, §22, §34).
 *
 * Selects the stub provider only when the build is explicitly compiled with VITE_FACE_PROVIDER=stub
 * (test/E2E builds). Production builds always use the real MediaPipe Face Landmarker. This is a
 * build-time dependency seam, not a runtime bypass.
 */

import type { EyeStateEvaluatorProvider } from './EyeStateEvaluatorProvider'
import { MediaPipeFaceLandmarker } from './MediaPipeFaceLandmarker'
import { StubEyeStateEvaluator } from './StubEyeStateEvaluator'

export function createEyeStateEvaluatorProvider(): EyeStateEvaluatorProvider {
  if (import.meta.env.VITE_FACE_PROVIDER === 'stub') {
    return new StubEyeStateEvaluator()
  }
  return new MediaPipeFaceLandmarker()
}
