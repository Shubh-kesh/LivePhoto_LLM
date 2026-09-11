/**
 * Primary normalized face-box form parameter for backend portrait processing.
 *
 * The M3/M5 quality engine already detects the primary face; its normalized bounding box is used
 * ONLY as geometry guidance for backend matte anchoring / crop / structural integrity validation.
 * It is never an authorization or security input, and no extra detector is added.
 */

import type { BundleQualityAssessment } from './types/quality'

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

/**
 * Format the selected frame's primary normalized face box as ``"x,y,w,h"`` (0..1), or undefined
 * when the assessment/frame/box is unavailable or degenerate. Backend treats it as guidance only.
 */
export function selectedFaceBoxParam(
  assessment: BundleQualityAssessment | null | undefined,
  frameId: string | undefined | null,
): string | undefined {
  if (!assessment || !frameId) return undefined
  const frame = assessment.frames.find((entry) => entry.frameId === frameId)
  const box = frame?.face.normalizedBoundingBox
  if (!box || box.width <= 0 || box.height <= 0) return undefined
  return [clamp01(box.x), clamp01(box.y), clamp01(box.width), clamp01(box.height)]
    .map((value) => value.toFixed(6))
    .join(',')
}