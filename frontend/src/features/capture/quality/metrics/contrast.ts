/**
 * Contrast metric (M3 §34): luminance standard deviation over the analysis buffer.
 *
 * Raw value; normalized only for UX scoring. Never presented as "image quality confidence".
 */

import type { AnalysisBuffer } from './types'

export function computeContrast(buffer: AnalysisBuffer): number {
  const { gray } = buffer
  const count = gray.length
  if (count === 0) return 0
  let sum = 0
  for (let i = 0; i < count; i += 1) sum += gray[i]
  const mean = sum / count
  let sumSq = 0
  for (let i = 0; i < count; i += 1) {
    const diff = gray[i] - mean
    sumSq += diff * diff
  }
  return Math.sqrt(sumSq / count)
}
