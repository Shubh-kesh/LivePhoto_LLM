/**
 * MediaPipe adapter translation tests (M3 §94). Pure mapping; no real-model inference.
 */

import { describe, expect, it } from 'vitest'

import { mapMediaPipeDetections } from '../face/MediaPipeFaceDetector'

describe('mapMediaPipeDetections', () => {
  it('maps bounding boxes to pixel and normalized coordinates with confidence', () => {
    const result = mapMediaPipeDetections(
      {
        detections: [
          {
            boundingBox: { originX: 100, originY: 80, width: 200, height: 200 },
            categories: [{ score: 0.93, categoryName: 'face' }],
            keypoints: [{ x: 150, y: 90 }],
          },
        ],
      },
      640,
      480,
    )
    expect(result).toHaveLength(1)
    const detection = result[0]
    expect(detection.confidence).toBeCloseTo(0.93, 3)
    expect(detection.boundingBox).toEqual({ x: 100, y: 80, width: 200, height: 200 })
    expect(detection.normalizedBoundingBox).toEqual({
      x: 100 / 640,
      y: 80 / 480,
      width: 200 / 640,
      height: 200 / 480,
    })
    expect(detection.keypoints).toEqual([{ x: 150, y: 90 }])
  })

  it('handles empty detections', () => {
    expect(mapMediaPipeDetections({ detections: [] }, 640, 480)).toEqual([])
  })

  it('is robust to missing fields', () => {
    const result = mapMediaPipeDetections({ detections: [{}] }, 640, 480)
    expect(result[0].confidence).toBe(0)
    expect(result[0].boundingBox).toEqual({ x: 0, y: 0, width: 0, height: 0 })
  })
})
