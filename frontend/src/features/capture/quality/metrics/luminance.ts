/**
 * Exposure / luminance metrics (M3 §30-33).
 *
 * - meanLuminance: mean of the grayscale analysis buffer (0..1).
 * - darkPixelRatio: fraction of pixels below the configured dark threshold.
 * - brightPixelRatio: fraction of pixels above the configured bright threshold.
 *
 * The dark/bright ratios catch clipping that mean brightness alone hides.
 */

import type { AnalysisBuffer } from './types'

export interface ExposureThresholds {
  darkPixelThreshold: number
  brightPixelThreshold: number
}

export function computeExposure(
  buffer: AnalysisBuffer,
  thresholds: ExposureThresholds,
): { meanLuminance: number; darkPixelRatio: number; brightPixelRatio: number } {
  const { gray } = buffer
  const count = gray.length
  if (count === 0) {
    return { meanLuminance: 0, darkPixelRatio: 0, brightPixelRatio: 0 }
  }
  let sum = 0
  let dark = 0
  let bright = 0
  for (let i = 0; i < count; i += 1) {
    const value = gray[i]
    sum += value
    if (value < thresholds.darkPixelThreshold) dark += 1
    if (value > thresholds.brightPixelThreshold) bright += 1
  }
  return {
    meanLuminance: sum / count,
    darkPixelRatio: dark / count,
    brightPixelRatio: bright / count,
  }
}
