/**
 * Deterministic stub eye-state evaluator (M5.7 §34, tests/E2E).
 *
 * Only compiled into builds explicitly configured with VITE_FACE_PROVIDER=stub. Behavior is driven
 * by the in-memory `window.__LIVEPHOTO_EYE_STUB__` global set via Playwright addInitScript.
 */

import type { EyeStateEvidence, FaceBoundingBox } from '../types/face'
import type { EyeStateEvaluatorProvider, EyeStateProviderState } from './EyeStateEvaluatorProvider'
import { uncertainEyeState } from './EyeStateEvaluatorProvider'

export type StubEyeMode = 'open' | 'left_closed' | 'right_closed' | 'closed' | 'unknown'

export interface StubEyeConfig {
  mode?: StubEyeMode
}

function readStubMode(): StubEyeMode {
  const config = (globalThis as { __LIVEPHOTO_EYE_STUB__?: StubEyeConfig }).__LIVEPHOTO_EYE_STUB__
  return config?.mode ?? 'open'
}

export class StubEyeStateEvaluator implements EyeStateEvaluatorProvider {
  readonly info = { name: 'stub-eye-state', version: '1.0.0', modelVersion: 'stub-v1' }
  state: EyeStateProviderState = 'NOT_INITIALIZED'

  async initialize(): Promise<void> {
    this.state = 'READY'
  }

  async evaluate(
    _image: CanvasImageSource,
    _primaryFaceBox: FaceBoundingBox,
  ): Promise<EyeStateEvidence> {
    const mode = readStubMode()
    if (mode === 'unknown') return uncertainEyeState()
    if (mode === 'left_closed') {
      return { evaluated: true, leftEyeOpen: false, rightEyeOpen: true, eyesOpen: false }
    }
    if (mode === 'right_closed') {
      return { evaluated: true, leftEyeOpen: true, rightEyeOpen: false, eyesOpen: false }
    }
    if (mode === 'closed') {
      return { evaluated: true, leftEyeOpen: false, rightEyeOpen: false, eyesOpen: false }
    }
    return { evaluated: true, leftEyeOpen: true, rightEyeOpen: true, eyesOpen: true }
  }

  dispose(): void {
    this.state = 'DISPOSED'
  }
}
