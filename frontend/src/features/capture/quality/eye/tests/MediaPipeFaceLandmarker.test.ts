/**
 * MediaPipe Face Landmarker eye-state translation tests (M5.7 §20, §31).
 *
 * Tests the deterministic `eyeStateFromLandmarkerResult` mapping (blendshape blink scores) and the
 * stub evaluator. No real model is required.
 */

import { describe, expect, it } from 'vitest'

import { eyeStateFromLandmarkerResult } from '../MediaPipeFaceLandmarker'
import { StubEyeStateEvaluator } from '../StubEyeStateEvaluator'

const PRIMARY_BOX = { x: 100, y: 80, width: 200, height: 200 }

function blendshapes(leftBlink: number, rightBlink: number) {
  return [
    {
      categories: [
        { categoryName: 'eyeBlinkLeft', score: leftBlink },
        { categoryName: 'eyeBlinkRight', score: rightBlink },
      ],
    },
  ]
}

function result(faces: unknown[][], shapeList: unknown[]) {
  return {
    faceLandmarks: faces,
    faceBlendshapes: shapeList,
  } as import('@mediapipe/tasks-vision').FaceLandmarkerResult
}

describe('eyeStateFromLandmarkerResult', () => {
  it('both eyes open (low blink scores)', () => {
    const state = eyeStateFromLandmarkerResult(
      result([landmarks(200, 200)], blendshapes(0.05, 0.08)),
      PRIMARY_BOX,
    )
    expect(state.evaluated).toBe(true)
    expect(state.eyesOpen).toBe(true)
    expect(state.leftEyeOpen).toBe(true)
    expect(state.rightEyeOpen).toBe(true)
  })

  it('left eye closed', () => {
    const state = eyeStateFromLandmarkerResult(
      result([landmarks(200, 200)], blendshapes(0.95, 0.05)),
      PRIMARY_BOX,
    )
    expect(state.evaluated).toBe(true)
    expect(state.leftEyeOpen).toBe(false)
    expect(state.rightEyeOpen).toBe(true)
    expect(state.eyesOpen).toBe(false)
  })

  it('right eye closed', () => {
    const state = eyeStateFromLandmarkerResult(
      result([landmarks(200, 200)], blendshapes(0.05, 0.96)),
      PRIMARY_BOX,
    )
    expect(state.eyesOpen).toBe(false)
    expect(state.rightEyeOpen).toBe(false)
  })

  it('both eyes closed', () => {
    const state = eyeStateFromLandmarkerResult(
      result([landmarks(200, 200)], blendshapes(0.97, 0.98)),
      PRIMARY_BOX,
    )
    expect(state.eyesOpen).toBe(false)
    expect(state.leftEyeOpen).toBe(false)
    expect(state.rightEyeOpen).toBe(false)
  })

  it('unknown when no faces or blendshapes are returned', () => {
    const noFaces = eyeStateFromLandmarkerResult(result([], []), PRIMARY_BOX)
    expect(noFaces.evaluated).toBe(false)
    expect(noFaces.eyesOpen).toBe(false)
    const noBlendshapes = eyeStateFromLandmarkerResult(
      result([landmarks(200, 200)], []),
      PRIMARY_BOX,
    )
    expect(noBlendshapes.evaluated).toBe(false)
    expect(noBlendshapes.eyesOpen).toBe(false)
  })

  it('matches the face nearest the primary face box', () => {
    const far = landmarks(30, 30) // background face (closed)
    const near = landmarks(200, 200) // primary face (open)
    const state = eyeStateFromLandmarkerResult(
      result([far, near], [blendshapes(0.95, 0.05)[0], blendshapes(0.05, 0.05)[0]]),
      PRIMARY_BOX,
    )
    // Primary (near) face eyes open; the background face's closed eyes must not affect the result.
    expect(state.eyesOpen).toBe(true)
  })
})

describe('StubEyeStateEvaluator', () => {
  it('returns deterministic modes', async () => {
    const stub = new StubEyeStateEvaluator()
    await stub.initialize()
    const anyImage = {} as CanvasImageSource
    const open = await stub.evaluate(anyImage, PRIMARY_BOX)
    expect(open.eyesOpen).toBe(true)
    stub.state = 'READY'
  })
})

function landmarks(cx: number, cy: number): Array<{ x: number; y: number }> {
  const points: Array<{ x: number; y: number }> = []
  for (let i = 0; i < 100; i += 1) {
    points.push({ x: cx - 50 + (i % 10), y: cy - 50 + Math.floor(i / 10) })
  }
  return points
}
