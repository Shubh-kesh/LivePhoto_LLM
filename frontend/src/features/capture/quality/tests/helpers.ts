/** Synthetic grayscale analysis buffers for deterministic metric tests (M3 §89). */

import type { AnalysisBuffer } from '../metrics/types'

export function grayBuffer(
  width: number,
  height: number,
  fill: (x: number, y: number) => number,
): AnalysisBuffer {
  const gray = new Float32Array(width * height)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      gray[y * width + x] = Math.min(1, Math.max(0, fill(x, y)))
    }
  }
  return { width, height, gray }
}

export function uniformGray(width: number, height: number, value: number): AnalysisBuffer {
  return grayBuffer(width, height, () => value)
}

/** Alternating low/high blocks (sharp edges, high contrast, mid mean, no extremes). */
export function checkerboardGray(
  width: number,
  height: number,
  low = 0.31,
  high = 0.7,
  block = 16,
): AnalysisBuffer {
  return grayBuffer(width, height, (x, y) => {
    const cell = Math.floor(x / block) + Math.floor(y / block)
    return cell % 2 === 0 ? low : high
  })
}

/** 3x3 box blur to produce a materially blurred version of a buffer (M3 §90). */
export function blurredCopy(buffer: AnalysisBuffer): AnalysisBuffer {
  const { width, height, gray } = buffer
  const out = new Float32Array(width * height)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let sum = 0
      let count = 0
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          const nx = x + dx
          const ny = y + dy
          if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
            sum += gray[ny * width + nx]
            count += 1
          }
        }
      }
      out[y * width + x] = sum / count
    }
  }
  return { width, height, gray: out }
}
