/**
 * MediaPipe Tasks Vision Face Landmarker eye-state evaluator (M5.7 §19-20, §37-38).
 *
 * Uses Face Landmarker blendshapes (`eyeBlinkLeft` / `eyeBlinkRight`) to determine whether the
 * primary face's eyes are open — the officially supported signal in the installed tasks-vision
 * version. Eye openness is capture quality only. The model/WASM are served from the
 * LivePhoto-controlled origin; eye processing stays in-memory in the browser.
 *
 * The MediaPipe module and Face Landmarker are loaded dynamically so stub builds never load them.
 */

import type { EyeStateEvidence, FaceBoundingBox } from '../types/face'
import type { EyeStateEvaluatorProvider, EyeStateProviderState } from './EyeStateEvaluatorProvider'
import { uncertainEyeState } from './EyeStateEvaluatorProvider'

type MpfFaceLandmarker = import('@mediapipe/tasks-vision').FaceLandmarker
type MpfResult = import('@mediapipe/tasks-vision').FaceLandmarkerResult

export const MEDIAPIPE_LANDMARKER_INFO = {
  name: 'mediapipe-face-landmarker',
  version: '1.0.0',
  modelVersion: 'face_landmarker float16 v1 (MediaPipe tasks-vision 1.0.1)',
}

const WASM_BASE_PATH = '/mediapipe-wasm'
const MODEL_ASSET_PATH = '/model-assets/face_landmarker.task'

//: Provisional capture-quality thresholds (M5.7 §45) — `eye-quality-v1`. Blink blendshape score
//: 0 = fully open, 1 = fully closed. Calibration may adjust these later; never inferred identity.
export const EYE_BLINK_OPEN_THRESHOLD = 0.5

export class MediaPipeFaceLandmarker implements EyeStateEvaluatorProvider {
  readonly info = MEDIAPIPE_LANDMARKER_INFO
  state: EyeStateProviderState = 'NOT_INITIALIZED'

  private landmarker: MpfFaceLandmarker | null = null

  async initialize(): Promise<void> {
    if (this.state === 'READY' || this.state === 'LOADING') return
    this.state = 'LOADING'
    try {
      const vision = await import('@mediapipe/tasks-vision')
      const fileset = await vision.FilesetResolver.forVisionTasks(WASM_BASE_PATH)
      this.landmarker = await vision.FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: MODEL_ASSET_PATH },
        runningMode: 'IMAGE',
        outputFaceBlendshapes: true,
        numFaces: 4,
      })
      this.state = 'READY'
    } catch (error) {
      this.state = 'ERROR'
      throw error
    }
  }

  async evaluate(
    image: CanvasImageSource,
    primaryFaceBox: FaceBoundingBox,
  ): Promise<EyeStateEvidence> {
    if (!this.landmarker || this.state !== 'READY') {
      return uncertainEyeState()
    }
    let result: MpfResult
    try {
      result = this.landmarker.detect(
        image as ImageData | HTMLImageElement | HTMLCanvasElement | HTMLVideoElement,
      )
    } catch {
      return uncertainEyeState()
    }
    return eyeStateFromLandmarkerResult(result, primaryFaceBox)
  }

  dispose(): void {
    if (this.landmarker) {
      try {
        this.landmarker.close()
      } catch {
        // Already closed.
      }
      this.landmarker = null
    }
    this.state = 'DISPOSED'
  }
}

interface FaceLandmark {
  x?: number
  y?: number
}

/**
 * Pick the landmarker face closest to the primary face box and derive eye openness from blendshapes.
 * If blendshapes are unavailable or the primary face cannot be matched reliably, the state is
 * UNKNOWN (conservative: the frame is never considered safe by default, M5.7 §27).
 */
export function eyeStateFromLandmarkerResult(
  result: MpfResult,
  primaryFaceBox: FaceBoundingBox,
): EyeStateEvidence {
  const faces = result.faceLandmarks ?? []
  const blendshapes = result.faceBlendshapes ?? []
  if (faces.length === 0) return uncertainEyeState()

  const primaryCenterX = primaryFaceBox.x + primaryFaceBox.width / 2
  const primaryCenterY = primaryFaceBox.y + primaryFaceBox.height / 2

  let bestIndex = 0
  let bestDistance = Number.POSITIVE_INFINITY
  faces.forEach((landmarks: FaceLandmark[], index: number) => {
    const box = landmarkBox(landmarks)
    if (!box) return
    const cx = box.x + box.width / 2
    const cy = box.y + box.height / 2
    const distance = Math.hypot(cx - primaryCenterX, cy - primaryCenterY)
    if (distance < bestDistance) {
      bestDistance = distance
      bestIndex = index
    }
  })

  if (bestDistance === Number.POSITIVE_INFINITY) return uncertainEyeState()
  const categories = blendshapes[bestIndex]?.categories ?? []
  if (categories.length === 0) return uncertainEyeState()

  const scoreFor = (name: string): number | null => {
    const category = categories.find((c) => c.categoryName === name)
    return typeof category?.score === 'number' ? category.score : null
  }
  const leftBlink = scoreFor('eyeBlinkLeft')
  const rightBlink = scoreFor('eyeBlinkRight')
  if (leftBlink === null || rightBlink === null) return uncertainEyeState()

  const leftEyeOpen = leftBlink <= EYE_BLINK_OPEN_THRESHOLD
  const rightEyeOpen = rightBlink <= EYE_BLINK_OPEN_THRESHOLD
  return {
    evaluated: true,
    leftEyeOpen,
    rightEyeOpen,
    eyesOpen: leftEyeOpen && rightEyeOpen,
  }
}

function landmarkBox(
  landmarks: FaceLandmark[],
): { x: number; y: number; width: number; height: number } | null {
  if (landmarks.length === 0) return null
  const xs = landmarks.map((l) => l.x ?? 0)
  const ys = landmarks.map((l) => l.y ?? 0)
  const x0 = Math.min(...xs)
  const y0 = Math.min(...ys)
  const x1 = Math.max(...xs)
  const y1 = Math.max(...ys)
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 }
}
