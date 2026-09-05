/**
 * Deterministic frame ranking (M3 §56-58).
 *
 * frame-ranking-v1: choose from eligible frames only, by:
 *   1. highest overallQualityScore
 *   2. higher face-detection confidence
 *   3. better (smaller) normalized center distance
 *   4. closeness to the temporal center of the burst
 *   5. earliest sequence as the final tie-break
 * No ML ranking.
 */

import { FRAME_RANKING_VERSION, type FrameQualityAssessment } from '../types/quality'

export interface FrameSelection {
  selectedId: string | null
  selectionScore?: number
  algorithmVersion: string
}

export function selectEligibleFrame(assessments: FrameQualityAssessment[]): FrameSelection {
  const eligible = assessments.filter((a) => a.disposition === 'ELIGIBLE')
  if (eligible.length === 0) {
    return { selectedId: null, algorithmVersion: FRAME_RANKING_VERSION }
  }

  const sequences = eligible.map((a) => a.sequence)
  const minSeq = Math.min(...sequences)
  const maxSeq = Math.max(...sequences)
  const middle = (minSeq + maxSeq) / 2

  const sorted = [...eligible].sort((a, b) => {
    const byQuality = b.scores.overallQuality - a.scores.overallQuality
    if (byQuality !== 0) return byQuality

    const confA = a.face.detectionConfidence ?? 0
    const confB = b.face.detectionConfidence ?? 0
    if (confB !== confA) return confB - confA

    const distA = a.face.centerOffset?.distance ?? Number.POSITIVE_INFINITY
    const distB = b.face.centerOffset?.distance ?? Number.POSITIVE_INFINITY
    if (distA !== distB) return distA - distB

    const centerA = Math.abs(a.sequence - middle)
    const centerB = Math.abs(b.sequence - middle)
    if (centerA !== centerB) return centerA - centerB

    return a.sequence - b.sequence
  })

  const selected = sorted[0]
  return {
    selectedId: selected.frameId,
    selectionScore: selected.scores.overallQuality,
    algorithmVersion: FRAME_RANKING_VERSION,
  }
}
