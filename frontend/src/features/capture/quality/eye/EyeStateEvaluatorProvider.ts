/**
 * EyeStateEvaluatorProvider contract (M5.7 §19-22).
 *
 * Evaluates whether the PRIMARY face's eyes are sufficiently open for photo capture. This is a
 * capture-quality gate only — NOT liveness, identity, emotion, health, age, gender or ethnicity
 * inference. Runs frontend-only; no eye images are ever sent to the backend.
 */

import type { EyeStateEvidence, FaceBoundingBox } from '../types/face'

export type EyeStateProviderState = 'NOT_INITIALIZED' | 'LOADING' | 'READY' | 'ERROR' | 'DISPOSED'

export interface EyeStateEvaluatorProvider {
  readonly info: { name: string; version: string; modelVersion: string }
  state: EyeStateProviderState
  initialize: () => Promise<void>
  /** Evaluate the primary face's eyes given its (pixel-space) bounding box. */
  evaluate: (image: CanvasImageSource, primaryFaceBox: FaceBoundingBox) => Promise<EyeStateEvidence>
  dispose: () => void
}

/** Conservative uncertain eye state: never considered safe by default (M5.7 §27). */
export function uncertainEyeState(): EyeStateEvidence {
  return { evaluated: false, leftEyeOpen: null, rightEyeOpen: null, eyesOpen: false }
}
