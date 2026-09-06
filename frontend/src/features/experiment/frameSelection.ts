/**
 * Frame selection for VLM upload (M4 §16-19, §22).
 *
 * Only quality-eligible frames are considered. single-quality-v1 sends the quality-selected frame;
 * temporal-triad-v1 sends the 3 eligible frames nearest 25/50/75% of burst chronology. If fewer
 * than 3 eligible frames exist, the triad returns [] and the caller reports a precondition result
 * rather than fabricating frames (M4 §18).
 */

import type { CaptureBundle, CaptureFrame } from '../capture/types/capture'
import type { BundleQualityAssessment } from '../capture/quality/types/quality'

export type ExperimentFrameStrategy = 'single-quality-v1' | 'temporal-triad-v1'

export function selectFramesForStrategy(
  bundle: CaptureBundle,
  quality: BundleQualityAssessment | null,
  strategy: ExperimentFrameStrategy,
): CaptureFrame[] {
  const eligibleIds = new Set(quality?.eligibleFrameIds ?? [])
  const eligible = bundle.frames
    .filter((frame) => eligibleIds.has(frame.id))
    .sort((a, b) => a.sequence - b.sequence)

  if (strategy === 'single-quality-v1') {
    const representative = bundle.frames.find((frame) => frame.id === bundle.representativeFrameId)
    return representative ? [representative] : eligible.slice(0, 1)
  }

  if (eligible.length < 3) return []
  const targets = [0.25, 0.5, 0.75]
  const picked: number[] = []
  for (const target of targets) {
    let index = Math.round(target * (eligible.length - 1))
    while (picked.includes(index)) {
      index = Math.min(eligible.length - 1, index + 1)
    }
    picked.push(index)
  }
  return picked.sort((a, b) => a - b).map((index) => eligible[index])
}
