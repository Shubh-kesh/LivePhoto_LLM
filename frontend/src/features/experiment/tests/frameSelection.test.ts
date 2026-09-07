/**
 * M4 frame-selection tests (M4 §16-19, §22).
 */

import { describe, expect, it } from 'vitest'

import type { CaptureBundle, CaptureFrame } from '../../capture/types/capture'
import type { BundleQualityAssessment } from '../../capture/quality/types/quality'
import { selectFramesForStrategy } from '../frameSelection'

function frame(id: string, sequence: number): CaptureFrame {
  return {
    id,
    sequence,
    capturedAtMs: sequence,
    blob: new Blob(['x']),
    mimeType: 'image/jpeg',
    width: 32,
    height: 32,
    byteSize: 1,
  }
}

function makeBundle(frameIds: string[]): CaptureBundle {
  const frames = frameIds.map((id, index) => frame(id, index))
  return {
    captureId: 'capture-1',
    createdAt: '2026-01-01T00:00:00Z',
    captureConfigVersion: 'capture-v1',
    camera: { facingMode: 'user' },
    frames,
    representativeFrameId: frames[Math.floor(frames.length / 2)].id,
  }
}

function qualityWith(eligibleIds: string[]): BundleQualityAssessment {
  return {
    captureId: 'capture-1',
    captureConfigVersion: 'capture-v1',
    qualityConfigVersion: 'quality-v1',
    frames: [],
    eligibleFrameIds: eligibleIds,
    selectedFrameId: eligibleIds[0],
    selectionAlgorithmVersion: 'frame-ranking-v2',
    disposition: 'QUALITY_READY',
    reasonCodes: [],
    totalAnalysisTimeMs: 1,
  }
}

describe('selectFramesForStrategy', () => {
  it('single-quality-v1 returns the quality-selected representative frame', () => {
    const bundle = makeBundle(['a', 'b', 'c', 'd', 'e'])
    const quality = qualityWith(['a', 'b', 'c', 'd', 'e'])
    const selected = selectFramesForStrategy(bundle, quality, 'single-quality-v1')
    expect(selected.map((f) => f.id)).toEqual([bundle.representativeFrameId])
  })

  it('temporal-triad-v1 picks eligible frames near 25/50/75% of chronology', () => {
    const bundle = makeBundle(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'])
    const quality = qualityWith(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'])
    const selected = selectFramesForStrategy(bundle, quality, 'temporal-triad-v1')
    expect(selected).toHaveLength(3)
    // Indexes nearest 25/50/75% of an 8-frame eligible set -> c(2), e(4), f(5).
    expect(selected.map((f) => f.id)).toEqual(['c', 'e', 'f'])
  })

  it('ignores ineligible frames for the triad', () => {
    const bundle = makeBundle(['a', 'b', 'c', 'd', 'e'])
    const quality = qualityWith(['b', 'd']) // only two eligible
    const selected = selectFramesForStrategy(bundle, quality, 'temporal-triad-v1')
    expect(selected).toEqual([])
  })

  it('returns no frames when fewer than 3 eligible frames exist (no fabrication)', () => {
    const bundle = makeBundle(['a', 'b'])
    const quality = qualityWith(['a', 'b'])
    expect(selectFramesForStrategy(bundle, quality, 'temporal-triad-v1')).toEqual([])
  })

  it('single still works with a subset of eligible frames', () => {
    const bundle = makeBundle(['a', 'b', 'c'])
    const quality = qualityWith(['b'])
    const selected = selectFramesForStrategy(bundle, quality, 'single-quality-v1')
    expect(selected.map((f) => f.id)).toEqual(['b'])
  })
})
