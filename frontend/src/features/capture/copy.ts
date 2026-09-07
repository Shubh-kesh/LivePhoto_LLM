/**
 * Centralized customer-facing copy (M5.5 §72-77). English for M5.5; structured so future
 * localization can swap the object without touching components. No technical/liveness language.
 */

import type { FlowError } from './hooks/flowError'
import type { QualityReasonCode } from './quality/types/quality'

export const captureCopy = {
  brand: {
    name: 'LivePhoto',
  },
  progress: {
    prepare: 'Prepare',
    capture: 'Capture',
    review: 'Review',
  },
  prepare: {
    title: 'Prepare for your photo',
    beforeWeBegin: 'Before we begin:',
    mask: 'Remove your mask',
    spectacles: 'Remove spectacles',
    faceVisible: 'Keep your face clearly visible',
    lighting: 'Find a well-lit place',
    footer: 'This will only take a few seconds.',
    continue: 'Continue',
  },
  permission: {
    title: 'Camera access',
    body: 'We need camera access to capture your photo.',
    microphone: 'Your microphone will not be used.',
    openCamera: 'Open camera',
    starting: 'Starting camera…',
  },
  camera: {
    help: 'Help',
    back: 'Back',
    switchCamera: 'Switch camera',
    capture: 'Capture photo',
    holdStill: 'Hold still…',
    checking: 'Checking photo quality…',
    ready: 'Ready to capture',
    detectorLoading: 'Preparing quality check…',
    detectorUnavailable: 'Quality check is unavailable.',
    positionFace: 'Position your face inside the guide.',
  },
  qualityRetry: {
    title: "Let's try again",
    generic: 'Your photo was a little blurry. Hold your device steady and try again.',
    unknown:
      "Let's try that photo again. Make sure your face is clearly visible and hold your device steady.",
    tryAgain: 'Try again',
    backToStart: 'Back to start',
  },
  review: {
    title: 'Your photo',
    body: 'Make sure your face is clearly visible.',
    retake: 'Retake photo',
    usePhoto: 'Use photo',
  },
  success: {
    title: 'Photo captured successfully',
    body: 'Your photo is ready.',
    startOver: 'Start over',
  },
  errors: {
    cameraAccessBlocked: {
      title: 'Camera access is blocked',
      body: 'LivePhoto needs camera access to capture your photo. Allow camera permission in your browser settings and try again.',
    },
    cameraBusy: {
      title: 'Camera is being used by another app',
      body: 'Close other apps using your camera and try again.',
    },
    cameraNotFound: {
      title: "We couldn't find a camera",
      body: 'Connect a camera and try again.',
    },
    unsupportedBrowser: {
      title: "Camera isn't available in this browser",
      body: 'Please open this link in a supported browser with camera access.',
    },
    cameraStartFailed: {
      title: "We couldn't start your camera",
      body: 'Please try again.',
    },
    cameraInterrupted: {
      title: 'Your camera was interrupted',
      body: 'Please try again.',
    },
    secureContext: {
      title: 'Camera requires a secure connection',
      body: 'Use HTTPS to open LivePhoto.',
    },
    qualityInternal: {
      title: 'Something went wrong while checking your photo',
      body: 'Please try again.',
    },
    cameraSwitch: {
      title: "We couldn't switch cameras",
      body: 'Your current camera is still active.',
    },
    generic: {
      title: 'Something went wrong',
      body: 'Please try again.',
    },
    tryAgain: 'Try again',
    backToStart: 'Back to start',
  },
  help: {
    title: 'Help',
    items: [
      'Remove your mask',
      'Remove spectacles',
      'Find good lighting',
      'Keep only one person visible',
      'Keep your device steady',
    ],
    close: 'Close',
  },
}

const retryReasonCopy: Partial<Record<QualityReasonCode, RetryCopy>> = {
  NO_FACE: {
    title: "We couldn't see your face clearly.",
    body: 'Position your face inside the guide.',
  },
  MULTIPLE_FACES: {
    title: 'Make sure only one person is visible.',
    body: 'Only one face should be in the photo.',
  },
  FACE_TOO_SMALL: {
    title: 'Move a little closer to the camera.',
    body: 'Your face should fill more of the photo.',
  },
  FACE_TOO_LARGE: {
    title: 'Move slightly away from the camera.',
    body: 'Your face should fit fully inside the guide.',
  },
  FACE_OFF_CENTER: {
    title: 'Move to the center of the frame.',
    body: 'Position your face inside the guide.',
  },
  UNDEREXPOSED: {
    title: 'Move to a brighter place.',
    body: 'Better lighting will help your photo.',
  },
  OVEREXPOSED: { title: 'Avoid very bright light behind you.', body: 'Face the light evenly.' },
  BLURRED: {
    title: 'Your photo was a little blurry.',
    body: 'Hold your device steady and try again.',
  },
  LOW_CONTRAST: { title: 'Improve the lighting.', body: 'Find a well-lit place and try again.' },
  RESOLUTION_TOO_LOW: {
    title: 'Move closer to the camera.',
    body: 'A closer, clearer photo works better.',
  },
  EYES_CLOSED: {
    title: 'Keep your eyes open and look at the camera.',
    body: 'Open eyes are needed for your photo.',
  },
  EYE_STATE_UNKNOWN: {
    title: 'Please look at the camera.',
    body: 'Keep your eyes open and look at the camera.',
  },
}

/** Map aggregated quality reason codes to a prioritized customer-facing retry message. */
const RETRY_PRIORITY: readonly QualityReasonCode[] = [
  'NO_FACE',
  'MULTIPLE_FACES',
  'FACE_TOO_SMALL',
  'FACE_TOO_LARGE',
  'UNDEREXPOSED',
  'OVEREXPOSED',
  'BLURRED',
  'FACE_OFF_CENTER',
  'LOW_CONTRAST',
  'EYES_CLOSED',
  'EYE_STATE_UNKNOWN',
]

export interface RetryCopy {
  title: string
  body: string
}

export function retryCopyForReasonCodes(reasonCodes: readonly QualityReasonCode[]): RetryCopy {
  for (const code of RETRY_PRIORITY) {
    if (reasonCodes.includes(code)) {
      const entry = retryReasonCopy[code]
      if (entry) return entry
    }
  }
  return {
    title: captureCopy.qualityRetry.unknown,
    body: captureCopy.qualityRetry.generic,
  }
}

export function internalRetryCopy(): RetryCopy {
  return { title: captureCopy.qualityRetry.unknown, body: captureCopy.qualityRetry.generic }
}

export interface ErrorCopy {
  title: string
  body: string
}

/** Map a flow error to customer-facing copy, separating camera/technical from quality errors. */
export function errorCopyFor(error: FlowError): ErrorCopy {
  if (error.type === 'quality') {
    return {
      title: captureCopy.errors.qualityInternal.title,
      body: captureCopy.errors.qualityInternal.body,
    }
  }
  switch (error.code) {
    case 'CAMERA_PERMISSION_DENIED':
      return {
        title: captureCopy.errors.cameraAccessBlocked.title,
        body: captureCopy.errors.cameraAccessBlocked.body,
      }
    case 'CAMERA_IN_USE_OR_UNREADABLE':
      return {
        title: captureCopy.errors.cameraBusy.title,
        body: captureCopy.errors.cameraBusy.body,
      }
    case 'CAMERA_NOT_FOUND':
      return {
        title: captureCopy.errors.cameraNotFound.title,
        body: captureCopy.errors.cameraNotFound.body,
      }
    case 'CAMERA_API_UNAVAILABLE':
      return {
        title: captureCopy.errors.unsupportedBrowser.title,
        body: captureCopy.errors.unsupportedBrowser.body,
      }
    case 'CAMERA_INTERRUPTED':
      return {
        title: captureCopy.errors.cameraInterrupted.title,
        body: captureCopy.errors.cameraInterrupted.body,
      }
    case 'INSECURE_CONTEXT':
      return {
        title: captureCopy.errors.secureContext.title,
        body: captureCopy.errors.secureContext.body,
      }
    case 'CAMERA_SWITCH_FAILED':
      return {
        title: captureCopy.errors.cameraSwitch.title,
        body: captureCopy.errors.cameraSwitch.body,
      }
    default:
      return {
        title: captureCopy.errors.cameraStartFailed.title,
        body: captureCopy.errors.cameraStartFailed.body,
      }
  }
}
