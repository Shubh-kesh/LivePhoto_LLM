/**
 * Quality-specific errors (M3 §113-115).
 *
 * Camera errors (technical) and quality evidence (image characteristics) are deliberately
 * separate taxonomies. A quality-engine exception maps to QUALITY_ANALYSIS_ERROR; a detector
 * failure maps to FACE_ANALYSIS_UNAVAILABLE — never to an image-quality classification such as
 * BLURRED or NO_FACE.
 */

import type { QualityReasonCode } from './types/quality'

export type QualityErrorCode = 'QUALITY_ANALYSIS_ERROR' | 'FACE_ANALYSIS_UNAVAILABLE'

const MESSAGES: Record<QualityErrorCode, string> = {
  QUALITY_ANALYSIS_ERROR: "We couldn't check photo quality. Please try again.",
  FACE_ANALYSIS_UNAVAILABLE: 'Face analysis is unavailable. Please try again later.',
}

export class QualityError extends Error {
  readonly code: QualityErrorCode
  readonly safeMessage: string
  readonly reasonCode: QualityReasonCode
  readonly type = 'quality' as const

  constructor(code: QualityErrorCode) {
    super(MESSAGES[code])
    this.name = 'QualityError'
    this.code = code
    this.safeMessage = MESSAGES[code]
    this.reasonCode =
      code === 'FACE_ANALYSIS_UNAVAILABLE' ? 'FACE_ANALYSIS_UNAVAILABLE' : 'QUALITY_ANALYSIS_ERROR'
  }
}
