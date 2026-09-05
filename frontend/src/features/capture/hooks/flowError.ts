/**
 * Flow error union (M3 §113-115).
 *
 * Technical camera errors and quality-analysis failures are distinct taxonomies and are kept
 * separate in the reducer/error UI.
 */

import type { CameraError } from '../media/mediaErrors'
import type { QualityError } from '../quality/errors'

export type FlowError = CameraError | QualityError

export function isQualityFlowError(error: FlowError): error is QualityError {
  return error.type === 'quality'
}

export function flowErrorMessage(error: FlowError): string {
  return error.safeMessage
}
