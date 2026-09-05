/**
 * Representative frame selection (M2 §34).
 *
 * M2 has no quality engine, so this is a deterministic neutral policy: the middle frame of the
 * successful burst. This is a temporary M2 policy and does NOT represent quality-based
 * best-frame selection. M3 replaces it with measurable quality ranking.
 */

import type { CaptureFrame } from '../types/capture'

export function selectRepresentativeFrame(frames: readonly CaptureFrame[]): CaptureFrame {
  if (frames.length === 0) {
    throw new Error('Cannot select a representative frame from an empty burst')
  }
  const middle = Math.floor((frames.length - 1) / 2)
  return frames[middle]
}
