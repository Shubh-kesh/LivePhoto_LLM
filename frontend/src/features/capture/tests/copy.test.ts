/**
 * Copy-mapping tests (M5.5 §32, §76-77): quality reason codes and flow errors are mapped to
 * customer copy, never raw codes.
 */

import { describe, expect, it } from 'vitest'

import { errorCopyFor, livenessRetryMessage, retryCopyForReasonCodes } from '../copy'
import { CameraError } from '../media/mediaErrors'
import { QualityError } from '../quality/errors'

describe('retryCopyForReasonCodes', () => {
  it('prioritizes the most actionable reason', () => {
    expect(retryCopyForReasonCodes(['BLURRED', 'NO_FACE']).title).toContain('face clearly')
    expect(retryCopyForReasonCodes(['UNDEREXPOSED']).body).toBe(
      'Better lighting will help your photo.',
    )
    expect(retryCopyForReasonCodes(['FACE_TOO_SMALL']).title).toBe(
      'Move a little closer to the camera.',
    )
    expect(retryCopyForReasonCodes(['FACE_TOO_LARGE']).title).toBe(
      'Move slightly away from the camera.',
    )
    expect(retryCopyForReasonCodes(['OVEREXPOSED']).title).toBe(
      'Avoid very bright light behind you.',
    )
  })

  it('falls back for unknown/technical failures without exposing codes', () => {
    const copy = retryCopyForReasonCodes(['QUALITY_ANALYSIS_ERROR'])
    expect(copy.title).toContain("Let's try that photo again")
    expect(JSON.stringify(copy)).not.toMatch(/QUALITY_ANALYSIS_ERROR|NO_FACE/)
  })
})

describe('livenessRetryMessage (backend single-person gate)', () => {
  it('maps MULTIPLE_FACES to the single-person copy', () => {
    expect(livenessRetryMessage(['MULTIPLE_FACES'])).toBe(
      'Make sure only one person is visible. Move to a place where no one else is in the photo.',
    )
  })

  it('maps NO_FACE to the no-face copy', () => {
    expect(livenessRetryMessage(['NO_FACE'])).toBe("We couldn't see your face clearly.")
  })

  it('falls back to a safe generic message and never exposes technical detail', () => {
    const message = livenessRetryMessage(undefined)
    expect(message).toBe("We couldn't use this photo. Please try again.")
    expect(message).not.toMatch(/vlm|groq|confidence|provider|model/i)
  })
})

describe('errorCopyFor', () => {
  it('separates quality errors from camera errors', () => {
    const quality = errorCopyFor(new QualityError('QUALITY_ANALYSIS_ERROR'))
    expect(quality.title).toBe('Something went wrong while checking your photo')
    const camera = errorCopyFor(new CameraError('CAMERA_PERMISSION_DENIED'))
    expect(camera.title).toBe('Camera access is blocked')
  })

  it('maps camera error codes to distinct customer messages', () => {
    expect(errorCopyFor(new CameraError('CAMERA_IN_USE_OR_UNREADABLE')).title).toBe(
      'Camera is being used by another app',
    )
    expect(errorCopyFor(new CameraError('CAMERA_API_UNAVAILABLE')).title).toBe(
      "Camera isn't available in this browser",
    )
    expect(errorCopyFor(new CameraError('CAMERA_NOT_FOUND')).title).toBe(
      "We couldn't find a camera",
    )
  })

  it('never surfaces the DOMException name', () => {
    const copy = errorCopyFor(new CameraError('CAMERA_PERMISSION_DENIED', 'NotAllowedError'))
    expect(JSON.stringify(copy)).not.toMatch(/NotAllowedError|DOMException/)
  })
})
