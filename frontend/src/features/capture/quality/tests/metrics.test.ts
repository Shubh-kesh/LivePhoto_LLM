/**
 * Pixel metric tests (M3 §89-92). All buffers are programmatically generated; no real images.
 */

import { describe, expect, it } from 'vitest'

import { computeExposure } from '../metrics/luminance'
import { computeContrast } from '../metrics/contrast'
import { computeSharpness } from '../metrics/sharpness'
import { luminanceOfRgb } from '../metrics/analysisImage'
import { blurredCopy, checkerboardGray, uniformGray } from './helpers'

const THRESHOLDS = { darkPixelThreshold: 0.1, brightPixelThreshold: 0.9 }

describe('luminance', () => {
  it('documented Rec.709 formula', () => {
    expect(luminanceOfRgb(255, 255, 255)).toBeCloseTo(1, 3)
    expect(luminanceOfRgb(0, 0, 0)).toBe(0)
    expect(luminanceOfRgb(255, 0, 0)).toBeCloseTo(0.2126, 3)
  })

  it('uniform dark image has high darkPixelRatio and low mean', () => {
    const metrics = computeExposure(uniformGray(64, 48, 0.05), THRESHOLDS)
    expect(metrics.meanLuminance).toBeCloseTo(0.05, 3)
    expect(metrics.darkPixelRatio).toBe(1)
    expect(metrics.brightPixelRatio).toBe(0)
  })

  it('uniform bright image has high brightPixelRatio and high mean', () => {
    const metrics = computeExposure(uniformGray(64, 48, 0.95), THRESHOLDS)
    expect(metrics.meanLuminance).toBeCloseTo(0.95, 3)
    expect(metrics.brightPixelRatio).toBe(1)
    expect(metrics.darkPixelRatio).toBe(0)
  })

  it('a normal synthetic image is inside the acceptable mean range with no extremes', () => {
    const metrics = computeExposure(checkerboardGray(64, 48, 0.31, 0.7), THRESHOLDS)
    expect(metrics.meanLuminance).toBeGreaterThan(0.4)
    expect(metrics.meanLuminance).toBeLessThan(0.6)
    expect(metrics.darkPixelRatio).toBe(0)
    expect(metrics.brightPixelRatio).toBe(0)
  })
})

describe('contrast', () => {
  it('uniform image has near-zero contrast', () => {
    expect(computeContrast(uniformGray(64, 48, 0.5))).toBeCloseTo(0, 3)
  })

  it('a mixed light/dark image has materially higher contrast', () => {
    const contrast = computeContrast(checkerboardGray(64, 48, 0.31, 0.7))
    expect(contrast).toBeGreaterThan(0.15)
  })
})

describe('sharpness', () => {
  it('uniform image has zero Laplacian variance', () => {
    expect(computeSharpness(uniformGray(64, 48, 0.5))).toBe(0)
  })

  it('sharp checkerboard is materially sharper than its blurred version', () => {
    const sharp = checkerboardGray(64, 48, 0.0, 1.0, 2)
    const blurred = blurredCopy(sharp)
    const sharpValue = computeSharpness(sharp)
    const blurredValue = computeSharpness(blurred)
    expect(sharpValue).toBeGreaterThan(0)
    expect(sharpValue).toBeGreaterThan(blurredValue * 2)
  })
})
