/**
 * Analysis image pipeline (M3 §28-29).
 *
 * Quality metrics are computed on a normalized analysis representation (preserve aspect ratio,
 * max dimension 640px) rather than arbitrary full-resolution images, so thresholds are less
 * device-dependent and processing is fast. Original CaptureFrame blobs are never modified;
 * analysis buffers are transient.
 */

import { QualityError } from '../errors'
import type { AnalysisBuffer } from './types'

/** Rec. 709 RGB -> luminance, normalized to 0..1 (documented formula, M3 §30). */
export function luminanceOfRgb(r: number, g: number, b: number): number {
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
}

export function sourceDimensions(source: CanvasImageSource): { width: number; height: number } {
  if (source instanceof HTMLVideoElement) {
    return { width: source.videoWidth, height: source.videoHeight }
  }
  if (source instanceof HTMLImageElement) {
    return { width: source.naturalWidth, height: source.naturalHeight }
  }
  if (source instanceof HTMLCanvasElement) {
    return { width: source.width, height: source.height }
  }
  const fallback = source as { width?: number; height?: number }
  if (typeof fallback.width === 'number' && typeof fallback.height === 'number') {
    return { width: fallback.width, height: fallback.height }
  }
  throw new QualityError('QUALITY_ANALYSIS_ERROR')
}

/** Downscale + convert a CanvasImageSource into a normalized grayscale analysis buffer. */
export function buildAnalysisBuffer(source: CanvasImageSource, maxDimension = 640): AnalysisBuffer {
  const { width: sourceWidth, height: sourceHeight } = sourceDimensions(source)
  if (sourceWidth <= 0 || sourceHeight <= 0) {
    throw new QualityError('QUALITY_ANALYSIS_ERROR')
  }
  const scale = Math.min(1, maxDimension / Math.max(sourceWidth, sourceHeight))
  const width = Math.max(1, Math.round(sourceWidth * scale))
  const height = Math.max(1, Math.round(sourceHeight * scale))

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) {
    throw new QualityError('QUALITY_ANALYSIS_ERROR')
  }
  context.drawImage(source, 0, 0, width, height)
  const imageData = context.getImageData(0, 0, width, height)

  const gray = new Float32Array(width * height)
  for (let i = 0; i < width * height; i += 1) {
    const offset = i * 4
    gray[i] = luminanceOfRgb(
      imageData.data[offset],
      imageData.data[offset + 1],
      imageData.data[offset + 2],
    )
  }
  return { width, height, gray }
}
