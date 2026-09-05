/**
 * Capture configuration constants (M2 §10, §35, §96).
 *
 * These values must be configuration constants, not duplicated magic numbers. They are NOT
 * backend environment variables yet; M3/M9 tune them based on evidence. Every CaptureBundle
 * records `configVersion` so that inputs affecting later model outcomes stay versionable.
 */

export const captureConfig = {
  configVersion: 'capture-v1',

  burstFrameCount: 8,
  burstDurationMs: 1200,
  minimumSuccessfulFrames: 6,

  preferredWidth: 1280,
  preferredHeight: 720,
  preferredFrameRate: 30,

  imageFormat: 'image/jpeg',
  jpegQuality: 0.95,

  defaultFacingMode: 'user',
} as const
