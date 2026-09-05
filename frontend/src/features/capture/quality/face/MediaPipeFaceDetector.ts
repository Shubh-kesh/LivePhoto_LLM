/**
 * MediaPipe Tasks Vision Face Detector implementation (M3 §8, §94).
 *
 * Model/WASM assets are served from the LivePhoto-controlled origin (never a public CDN at
 * inference time); see frontend/model-assets/ and scripts/setup-face-assets.sh.
 *
 * The MediaPipe module is imported dynamically inside initialize() so that builds using the stub
 * provider never load the wasm/model.
 */

import type { FaceDetectionResult, FaceDetectorInfo } from '../types/face'
import type { FaceDetectorProvider, FaceDetectorProviderState } from './FaceDetectorProvider'

// Type-only import (erased at build time); the runtime import happens in initialize().
type MpfFaceDetector = import('@mediapipe/tasks-vision').FaceDetector

export const MEDIAPIPE_DETECTOR_INFO: FaceDetectorInfo = {
  name: 'mediapipe-face-detector',
  version: '1.0.0',
  modelVersion: 'face_detector short-range v0.4',
}

const WASM_BASE_PATH = '/mediapipe-wasm'
const MODEL_ASSET_PATH = '/model-assets/face_detector.task'

export class MediaPipeFaceDetector implements FaceDetectorProvider {
  readonly info: FaceDetectorInfo = MEDIAPIPE_DETECTOR_INFO
  state: FaceDetectorProviderState = 'NOT_INITIALIZED'

  private detector: MpfFaceDetector | null = null

  async initialize(): Promise<void> {
    if (this.state === 'READY' || this.state === 'LOADING') return
    this.state = 'LOADING'
    try {
      const vision = await import('@mediapipe/tasks-vision')
      const fileset = await vision.FilesetResolver.forVisionTasks(WASM_BASE_PATH)
      this.detector = await vision.FaceDetector.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: MODEL_ASSET_PATH },
        runningMode: 'IMAGE',
      })
      this.state = 'READY'
    } catch (error) {
      this.state = 'ERROR'
      throw error
    }
  }

  async detect(image: CanvasImageSource): Promise<FaceDetectionResult> {
    if (!this.detector || this.state !== 'READY') {
      throw new Error('MediaPipe face detector is not ready')
    }
    const { width, height } = sourceSize(image)
    const started = performance.now()
    const result = this.detector.detect(
      image as ImageData | HTMLImageElement | HTMLCanvasElement | HTMLVideoElement,
    )
    const inferenceTimeMs = performance.now() - started
    return {
      detections: mapMediaPipeDetections(result, width, height),
      imageWidth: width,
      imageHeight: height,
      inferenceTimeMs,
    }
  }

  dispose(): void {
    if (this.detector) {
      try {
        this.detector.close()
      } catch {
        // Detector already closed.
      }
      this.detector = null
    }
    this.state = 'DISPOSED'
  }
}

function sourceSize(source: CanvasImageSource): { width: number; height: number } {
  if (source instanceof HTMLVideoElement)
    return { width: source.videoWidth, height: source.videoHeight }
  if (source instanceof HTMLImageElement)
    return { width: source.naturalWidth, height: source.naturalHeight }
  if (source instanceof HTMLCanvasElement) return { width: source.width, height: source.height }
  const fallback = source as { width?: number; height?: number }
  return { width: fallback.width ?? 0, height: fallback.height ?? 0 }
}

interface MediaPipeDetection {
  boundingBox?: {
    originX?: number
    originY?: number
    width?: number
    height?: number
  }
  categories?: Array<{ score?: number; categoryName?: string }>
  keypoints?: Array<{ x?: number; y?: number }>
}

/**
 * Pure translation from MediaPipe-shaped detections into our normalized FaceDetection (M3 §19,
 * §94). Extracted for deterministic unit tests without real-model inference.
 */
export function mapMediaPipeDetections(
  result: { detections?: MediaPipeDetection[] },
  imageWidth: number,
  imageHeight: number,
): FaceDetectionResult['detections'] {
  const detections = (result.detections ?? []) as MediaPipeDetection[]
  return detections.map((detection) => {
    const box = detection.boundingBox ?? {}
    const rawBox = {
      x: box.originX ?? 0,
      y: box.originY ?? 0,
      width: box.width ?? 0,
      height: box.height ?? 0,
    }
    return {
      confidence: detection.categories?.[0]?.score ?? 0,
      boundingBox: rawBox,
      normalizedBoundingBox: {
        x: imageWidth > 0 ? rawBox.x / imageWidth : 0,
        y: imageHeight > 0 ? rawBox.y / imageHeight : 0,
        width: imageWidth > 0 ? rawBox.width / imageWidth : 0,
        height: imageHeight > 0 ? rawBox.height / imageHeight : 0,
      },
      keypoints: detection.keypoints?.map((kp) => ({ x: kp.x ?? 0, y: kp.y ?? 0 })),
    }
  })
}
