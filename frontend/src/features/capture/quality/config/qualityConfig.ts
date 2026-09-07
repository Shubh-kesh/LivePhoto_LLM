/**
 * Quality configuration (M3 §39-40, §108).
 *
 * All thresholds are PROVISIONAL, NOT CALIBRATED and NOT BANK-APPROVED. They exist to establish
 * functionality; M9 calibrates them using evaluation data. See docs/QUALITY_CONFIGURATION.md for
 * the full register. Changing any threshold/analysis setting requires a new QUALITY_CONFIG_VERSION
 * because Laplacian variance and normalization depend on preprocessing (M3 §36).
 */

export const QUALITY_CONFIG_VERSION = 'quality-v1'

export const qualityConfig = {
  configVersion: QUALITY_CONFIG_VERSION,

  analysis: {
    maxAnalysisDimension: 640,
    previewAnalysisRateHz: 3,
    previewStabilizationCount: 2,
    readyStabilizationCount: 2,
  },

  face: {
    minDetectionConfidence: 0.5,
    minFaceCoverage: 0.08,
    maxFaceCoverage: 0.6,
    maxCenterOffsetX: 0.25,
    maxCenterOffsetY: 0.3,
  },

  // Closed-eye capture gate (M5.7 §45). PROVISIONAL capture-quality thresholds (`eye-quality-v1`),
  // not calibrated and not universal-accuracy claims. Eye openness is capture quality only.
  eye: {
    version: 'eye-quality-v1',
    // Face Landmarker blendshape score: 0 = fully open, 1 = fully closed.
    blinkOpenThreshold: 0.5,
    // A frame whose eye state cannot be evaluated is never considered safe by default.
    requireEvaluation: true,
  },

  exposure: {
    minMeanLuminance: 0.25,
    maxMeanLuminance: 0.85,
    darkPixelThreshold: 0.1,
    maxDarkPixelRatio: 0.4,
    brightPixelThreshold: 0.9,
    maxBrightPixelRatio: 0.35,
  },

  contrast: {
    // Reference luminance standard deviation used for normalization.
    minContrast: 0.08,
  },

  sharpness: {
    // Reference "variance of Laplacian"; higher = sharper, lower = blurrier.
    blurThreshold: 100,
    kernel: '3x3-laplacian',
  },

  resolution: {
    minWidth: 320,
    minHeight: 240,
  },

  bundle: {
    minimumEligibleFrames: 3,
    reasonAggregationMinimum: 3,
  },

  scoring: {
    // overallQualityScore = minimum of applicable component scores (M3 §49).
    overallMode: 'min',
  },

  guidance: {
    readyScoreThreshold: 0.7,
  },
} as const

export type QualityConfig = typeof qualityConfig
