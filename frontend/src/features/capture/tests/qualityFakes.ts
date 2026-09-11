/**
 * Deterministic quality fakes for tests (M3 §93, §100-102).
 *
 * A configurable fake FaceDetectorProvider and helpers that build BundleQualityAssessment
 * fixtures for flow tests (QUALITY_READY / QUALITY_RETRY / ANALYSIS_UNAVAILABLE).
 */

import type { FaceDetectionResult, FaceDetectorInfo } from '../quality/types/face'
import type {
  FaceDetectorProvider,
  FaceDetectorProviderState,
} from '../quality/face/FaceDetectorProvider'
import type { EyeStateEvidence, FaceBoundingBox } from '../quality/types/face'
import type {
  EyeStateEvaluatorProvider,
  EyeStateProviderState,
} from '../quality/eye/EyeStateEvaluatorProvider'
import type {
  BundleQualityAssessment,
  FrameQualityAssessment,
  QualityReasonCode,
} from '../quality/types/quality'
import { FRAME_RANKING_VERSION } from '../quality/types/quality'
import type { CaptureBundle } from '../types/capture'

const FAKE_INFO: FaceDetectorInfo = {
  name: 'fake-face-detector',
  version: '0.0.1',
  modelVersion: 'fake-v1',
}

export type FakeFaceMode = 'good' | 'noface' | 'toosmall' | 'toolarge' | 'multiple'

export class FakeFaceDetector implements FaceDetectorProvider {
  readonly info: FaceDetectorInfo = FAKE_INFO
  state: FaceDetectorProviderState = 'NOT_INITIALIZED'
  mode: FakeFaceMode = 'good'
  detectCalls = 0
  initializeCalls = 0
  disposeCalls = 0
  failDetect = false

  async initialize(): Promise<void> {
    this.initializeCalls += 1
    this.state = 'READY'
  }

  async detect(): Promise<FaceDetectionResult> {
    this.detectCalls += 1
    if (this.failDetect) throw new Error('detector failure')
    return fakeDetectionResult(this.mode)
  }

  dispose(): void {
    this.disposeCalls += 1
    this.state = 'DISPOSED'
  }
}

export type FakeEyeMode = 'open' | 'left_closed' | 'right_closed' | 'closed' | 'unknown'

/** Deterministic eye-state evaluator for tests/E2E (M5.7 §31-33). */
export class FakeEyeStateEvaluator implements EyeStateEvaluatorProvider {
  readonly info = { name: 'fake-eye-state', version: '0.0.1', modelVersion: 'fake-v1' }
  state: EyeStateProviderState = 'NOT_INITIALIZED'
  mode: FakeEyeMode = 'open'
  evaluateCalls = 0

  async initialize(): Promise<void> {
    this.state = 'READY'
  }

  async evaluate(
    _image: CanvasImageSource,
    _primaryFaceBox: FaceBoundingBox,
  ): Promise<EyeStateEvidence> {
    this.evaluateCalls += 1
    if (this.mode === 'unknown') {
      return { evaluated: false, leftEyeOpen: null, rightEyeOpen: null, eyesOpen: false }
    }
    if (this.mode === 'left_closed') {
      return { evaluated: true, leftEyeOpen: false, rightEyeOpen: true, eyesOpen: false }
    }
    if (this.mode === 'right_closed') {
      return { evaluated: true, leftEyeOpen: true, rightEyeOpen: false, eyesOpen: false }
    }
    if (this.mode === 'closed') {
      return { evaluated: true, leftEyeOpen: false, rightEyeOpen: false, eyesOpen: false }
    }
    return { evaluated: true, leftEyeOpen: true, rightEyeOpen: true, eyesOpen: true }
  }

  dispose(): void {
    this.state = 'DISPOSED'
  }
}

export function fakeDetectionResult(mode: FakeFaceMode): FaceDetectionResult {
  const base: FaceDetectionResult = {
    detections: [],
    imageWidth: 640,
    imageHeight: 480,
    inferenceTimeMs: 0,
  }
  if (mode === 'noface') return base
  if (mode === 'multiple') {
    base.detections.push(
      {
        confidence: 0.9,
        boundingBox: { x: 40, y: 60, width: 200, height: 200 },
        normalizedBoundingBox: { x: 40 / 640, y: 60 / 480, width: 200 / 640, height: 200 / 480 },
      },
      {
        confidence: 0.85,
        boundingBox: { x: 360, y: 100, width: 180, height: 180 },
        normalizedBoundingBox: { x: 360 / 640, y: 100 / 480, width: 180 / 640, height: 180 / 480 },
      },
    )
    return base
  }
  let width = 300
  let height = 300
  if (mode === 'toosmall') {
    width = 30
    height = 30
  }
  if (mode === 'toolarge') {
    width = 620
    height = 480
  }
  base.detections.push({
    confidence: 0.95,
    boundingBox: { x: (640 - width) / 2, y: (480 - height) / 2, width, height },
    normalizedBoundingBox: {
      x: (640 - width) / 2 / 640,
      y: (480 - height) / 2 / 480,
      width: width / 640,
      height: height / 480,
    },
  })
  return base
}

function eligibleAssessment(bundle: CaptureBundle, index: number): FrameQualityAssessment {
  const frame = bundle.frames[index]
  const width = frame.width
  const height = frame.height
  return {
    frameId: frame.id,
    sequence: frame.sequence,
    configVersion: 'quality-v1',
    dimensions: { width, height, pixelCount: width * height },
    face: {
      count: 1,
      detectionConfidence: 0.95,
      coverageRatio: 0.3,
      centerOffset: { dx: 0, dy: 0, distance: 0 },
      normalizedBoundingBox: { x: 0.25, y: 0.2, width: 0.5, height: 0.5 },
    },
    exposure: { meanLuminance: 0.5, darkPixelRatio: 0.05, brightPixelRatio: 0.05 },
    contrast: { rawValue: 0.2 },
    sharpness: { rawValue: 300 },
    scores: {
      face: 0.95,
      exposure: 0.95,
      contrast: 1,
      sharpness: 1,
      overallQuality: 0.9,
    },
    metricResults: [],
    reasonCodes: [],
    disposition: 'ELIGIBLE',
    analysisTimeMs: 1,
  }
}

function middleIndex(count: number): number {
  return Math.floor((count - 1) / 2)
}

export function readyBundleAssessment(bundle: CaptureBundle): BundleQualityAssessment {
  const frames = bundle.frames.map((_, index) => eligibleAssessment(bundle, index))
  const selected = frames[middleIndex(frames.length)]
  return {
    captureId: bundle.captureId,
    captureConfigVersion: bundle.captureConfigVersion,
    qualityConfigVersion: 'quality-v1',
    frames,
    eligibleFrameIds: frames.map((f) => f.frameId),
    selectedFrameId: selected.frameId,
    selectionAlgorithmVersion: FRAME_RANKING_VERSION,
    selectionScore: selected.scores.overallQuality,
    disposition: 'QUALITY_READY',
    reasonCodes: [],
    totalAnalysisTimeMs: frames.length,
  }
}

export function retryBundleAssessment(
  bundle: CaptureBundle,
  reasonCodes: QualityReasonCode[] = ['NO_FACE'],
): BundleQualityAssessment {
  const frames = bundle.frames.map((frame, index) => ({
    frameId: frame.id,
    sequence: index,
    configVersion: 'quality-v1',
    dimensions: {
      width: frame.width,
      height: frame.height,
      pixelCount: frame.width * frame.height,
    },
    face: { count: 0 },
    exposure: { meanLuminance: 0.5, darkPixelRatio: 0.05, brightPixelRatio: 0.05 },
    contrast: { rawValue: 0.2 },
    sharpness: { rawValue: 300 },
    scores: { face: 0, exposure: 0.95, contrast: 1, sharpness: 1, overallQuality: 0 },
    metricResults: [],
    reasonCodes,
    disposition: 'INELIGIBLE' as const,
    analysisTimeMs: 1,
  }))
  return {
    captureId: bundle.captureId,
    captureConfigVersion: bundle.captureConfigVersion,
    qualityConfigVersion: 'quality-v1',
    frames,
    eligibleFrameIds: [],
    selectionAlgorithmVersion: FRAME_RANKING_VERSION,
    disposition: 'QUALITY_RETRY',
    reasonCodes,
    totalAnalysisTimeMs: frames.length,
  }
}

export function unavailableBundleAssessment(bundle: CaptureBundle): BundleQualityAssessment {
  const frames = bundle.frames.map((frame, index) => ({
    frameId: frame.id,
    sequence: index,
    configVersion: 'quality-v1',
    dimensions: { width: 0, height: 0, pixelCount: 0 },
    face: { count: 0 },
    exposure: { meanLuminance: 0, darkPixelRatio: 0, brightPixelRatio: 0 },
    contrast: { rawValue: 0 },
    sharpness: { rawValue: 0 },
    scores: { exposure: 0, contrast: 0, sharpness: 0, overallQuality: 0 },
    metricResults: [],
    reasonCodes: ['QUALITY_ANALYSIS_ERROR'] as QualityReasonCode[],
    disposition: 'ANALYSIS_UNAVAILABLE' as const,
    analysisTimeMs: 0,
  }))
  return {
    captureId: bundle.captureId,
    captureConfigVersion: bundle.captureConfigVersion,
    qualityConfigVersion: 'quality-v1',
    frames,
    eligibleFrameIds: [],
    selectionAlgorithmVersion: FRAME_RANKING_VERSION,
    disposition: 'ANALYSIS_UNAVAILABLE',
    reasonCodes: ['QUALITY_ANALYSIS_ERROR'],
    totalAnalysisTimeMs: 0,
  }
}
