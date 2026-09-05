/**
 * Face geometry helpers (M3 §20, §24-25).
 *
 * Normalized coordinates (0..1 relative to frame dimensions) make policy rules resolution
 * independent. Face centering is NOT head pose (M3 §26).
 */

import type { FaceBoundingBox } from '../types/face'

export interface NormalizedBox {
  x: number
  y: number
  width: number
  height: number
}

export function normalizeBox(
  box: FaceBoundingBox,
  imageWidth: number,
  imageHeight: number,
): NormalizedBox {
  return {
    x: box.x / imageWidth,
    y: box.y / imageHeight,
    width: box.width / imageWidth,
    height: box.height / imageHeight,
  }
}

/** Face bounding-box area as a fraction of the frame area (M3 §24). */
export function faceCoverageRatio(normalized: NormalizedBox): number {
  return Math.max(0, normalized.width) * Math.max(0, normalized.height)
}

/** Normalized face-center offset from the frame center (M3 §25). */
export function faceCenterOffset(normalized: NormalizedBox): {
  dx: number
  dy: number
  distance: number
} {
  const cx = normalized.x + normalized.width / 2
  const cy = normalized.y + normalized.height / 2
  const dx = cx - 0.5
  const dy = cy - 0.5
  return { dx, dy, distance: Math.sqrt(dx * dx + dy * dy) }
}

/** Clamp a value to [0, 1]. */
export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}
