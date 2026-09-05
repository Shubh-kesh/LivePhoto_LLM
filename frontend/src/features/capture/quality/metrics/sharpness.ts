/**
 * Sharpness / blur metric (M3 §35-37): variance of the Laplacian over the grayscale analysis
 * buffer. Higher = sharper, lower = blurrier. Computed on 0..255-scaled luminance (equivalent to
 * 8-bit grayscale), so values align with conventional Laplacian-variance ranges. The raw value is
 * only comparable for the SAME preprocessing configuration (analysis resolution, kernel, quality
 * config version).
 */

import type { AnalysisBuffer } from './types'

/** 3x3 Laplacian kernel (M3 §36). */
export const LAPLACIAN_KERNEL = '3x3-laplacian'

/** Scale from normalized (0..1) luminance to 8-bit grayscale (0..255) for the Laplacian. */
const LUMINANCE_SCALE = 255

export function computeSharpness(buffer: AnalysisBuffer): number {
  const { width, height, gray } = buffer
  if (width < 3 || height < 3) return 0

  const lap = new Float32Array(width * height)
  let sumLap = 0
  let sumSq = 0
  let count = 0
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const i = y * width + x
      const value =
        LUMINANCE_SCALE *
        (4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - width] - gray[i + width])
      lap[i] = value
      sumLap += value
      sumSq += value * value
      count += 1
    }
  }
  if (count === 0) return 0
  const meanLap = sumLap / count
  const variance = sumSq / count - meanLap * meanLap
  return Math.max(0, variance)
}
