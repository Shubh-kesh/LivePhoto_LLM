/**
 * Quality subsystem for LivePhoto (M3).
 *
 * Client-side preliminary quality/face-acquisition evidence. NOT an authoritative security result,
 * NOT a liveness decision.
 */

export * from './types/quality'
export * from './types/face'
export * from './config/qualityConfig'
export * from './errors'
export * from './face/FaceDetectorProvider'
export * from './face/faceDetectorFactory'
export * from './guidance/guidance'
export { analyzeFrame } from './engine/frameAnalyzer'
export { analyzeBundle, decodeFrameImage } from './engine/bundleAnalyzer'
export { selectEligibleFrame } from './engine/frameRanking'
export { StubFaceDetector } from './face/StubFaceDetector'
