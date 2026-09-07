/**
 * Customer guidance (M3 §62-65, §81-82).
 *
 * Guidance is capture-quality language only ("Face detected", "Move closer", "Hold still",
 * "Ready to capture") — never liveness language. "Ready to capture" means the current preview
 * quality appears suitable, NOT that the subject is verified.
 *
 * Stabilization: guidance categories only change after the same category is observed for a
 * configurable number of consecutive analyses (M3 §81-82).
 */

import type { FrameQualityAssessment, QualityReasonCode } from '../types/quality'

export type GuidanceCategory =
  | 'NEUTRAL'
  | 'NO_FACE'
  | 'MULTIPLE_FACES'
  | 'TOO_CLOSE'
  | 'TOO_FAR'
  | 'OFF_CENTER'
  | 'EXPOSURE'
  | 'BLUR'
  | 'LOW_CONTRAST'
  | 'EYES_CLOSED'
  | 'READY'

export type GuideVisualState = 'neutral' | 'guidance' | 'ready'

export interface LiveGuidance {
  category: GuidanceCategory
  message: string
  guideState: GuideVisualState
}

const MESSAGES: Record<GuidanceCategory, string> = {
  NEUTRAL: 'Position your face inside the guide.',
  NO_FACE: 'Position your face inside the guide.',
  MULTIPLE_FACES: 'Make sure only one person is visible.',
  TOO_CLOSE: 'Move a little farther from the camera.',
  TOO_FAR: 'Move closer to the camera.',
  OFF_CENTER: 'Move slightly to the center.',
  EXPOSURE: 'Improve the lighting.',
  BLUR: 'Hold still.',
  LOW_CONTRAST: 'Improve the lighting.',
  EYES_CLOSED: 'Open your eyes and look at the camera.',
  READY: 'Ready to capture.',
}

export function guidanceMessage(category: GuidanceCategory): string {
  return MESSAGES[category]
}

/**
 * Priority for live guidance (M3 §63): the first matching category wins.
 */
const LIVE_PRIORITY: Array<{ reason: QualityReasonCode | null; category: GuidanceCategory }> = [
  { reason: 'NO_FACE', category: 'NO_FACE' },
  { reason: 'MULTIPLE_FACES', category: 'MULTIPLE_FACES' },
  { reason: 'FACE_TOO_SMALL', category: 'TOO_FAR' },
  { reason: 'FACE_TOO_LARGE', category: 'TOO_CLOSE' },
  { reason: 'UNDEREXPOSED', category: 'EXPOSURE' },
  { reason: 'OVEREXPOSED', category: 'EXPOSURE' },
  { reason: 'BLURRED', category: 'BLUR' },
  { reason: 'LOW_CONTRAST', category: 'LOW_CONTRAST' },
  { reason: 'FACE_OFF_CENTER', category: 'OFF_CENTER' },
  { reason: 'EYES_CLOSED', category: 'EYES_CLOSED' },
  { reason: 'EYE_STATE_UNKNOWN', category: 'EYES_CLOSED' },
]

/** Map a live FrameQualityAssessment to the highest-priority guidance category. */
export function categoryFromAssessment(
  assessment: FrameQualityAssessment,
  readyScoreThreshold = 0.7,
): GuidanceCategory {
  const { reasonCodes, scores } = assessment
  for (const entry of LIVE_PRIORITY) {
    if (entry.reason !== null && reasonCodes.includes(entry.reason)) {
      return entry.category
    }
  }
  if (scores.overallQuality >= readyScoreThreshold) return 'READY'
  return 'NEUTRAL'
}

/**
 * Guidance stabilizer (M3 §81-82): returns the category only after it has been observed for
 * `requiredConsistency` consecutive analyses.
 */
export class GuidanceStabilizer {
  private current: GuidanceCategory | null = null
  private count = 0

  constructor(private readonly requiredConsistency: number) {}

  update(category: GuidanceCategory): GuidanceCategory | null {
    if (category === this.current) {
      this.count += 1
    } else {
      this.current = category
      this.count = 1
    }
    return this.count >= this.requiredConsistency ? this.current : null
  }

  reset(): void {
    this.current = null
    this.count = 0
  }
}

/**
 * Priority for QUALITY_RETRY guidance (M3 §62-63): maps the bundle's aggregated reason codes to
 * the single most useful customer action.
 */
const RETRY_PRIORITY: Array<{ reason: QualityReasonCode; category: GuidanceCategory }> = [
  { reason: 'NO_FACE', category: 'NO_FACE' },
  { reason: 'MULTIPLE_FACES', category: 'MULTIPLE_FACES' },
  { reason: 'FACE_TOO_SMALL', category: 'TOO_FAR' },
  { reason: 'FACE_TOO_LARGE', category: 'TOO_CLOSE' },
  { reason: 'UNDEREXPOSED', category: 'EXPOSURE' },
  { reason: 'OVEREXPOSED', category: 'EXPOSURE' },
  { reason: 'BLURRED', category: 'BLUR' },
  { reason: 'FACE_OFF_CENTER', category: 'OFF_CENTER' },
  { reason: 'LOW_CONTRAST', category: 'LOW_CONTRAST' },
  { reason: 'EYES_CLOSED', category: 'EYES_CLOSED' },
  { reason: 'EYE_STATE_UNKNOWN', category: 'EYES_CLOSED' },
]

export function guidanceFromReasonCodes(reasonCodes: QualityReasonCode[]): GuidanceCategory {
  for (const entry of RETRY_PRIORITY) {
    if (reasonCodes.includes(entry.reason)) return entry.category
  }
  return 'NEUTRAL'
}

export function buildLiveGuidance(category: GuidanceCategory): LiveGuidance {
  const guideState: GuideVisualState =
    category === 'READY' ? 'ready' : category === 'NEUTRAL' ? 'neutral' : 'guidance'
  return { category, message: guidanceMessage(category), guideState }
}
