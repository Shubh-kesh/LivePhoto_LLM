/**
 * useLiveQuality — low-frequency live preview analysis (M3 §15-18, §79-82).
 *
 * Runs one analysis at a time at ~3 Hz (configurable) with latest-frame-wins; if an analysis is
 * still running when the next interval fires, that analysis opportunity is skipped (no unbounded
 * queue). Guidance is stabilized (same category for N consecutive analyses) to avoid flickering.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'

import { qualityConfig } from '../quality/config/qualityConfig'
import { analyzeFrame } from '../quality/engine/frameAnalyzer'
import type {
  FaceDetectorProvider,
  FaceDetectorProviderState,
} from '../quality/face/FaceDetectorProvider'
import {
  buildLiveGuidance,
  categoryFromAssessment,
  GuidanceStabilizer,
  type GuidanceCategory,
  type LiveGuidance,
} from '../quality/guidance/guidance'
import type { FrameQualityAssessment } from '../quality/types/quality'

export interface UseLiveQualityOptions {
  videoRef: RefObject<HTMLVideoElement | null>
  detector: FaceDetectorProvider
  enabled: boolean
}

export interface UseLiveQualityResult {
  detectorState: FaceDetectorProviderState
  snapshot: FrameQualityAssessment | null
  guidance: LiveGuidance | null
  isReady: boolean
  analysisTimeMs: number | null
}

export function useLiveQuality({
  videoRef,
  detector,
  enabled,
}: UseLiveQualityOptions): UseLiveQualityResult {
  const [detectorState, setDetectorState] = useState<FaceDetectorProviderState>('NOT_INITIALIZED')
  const [snapshot, setSnapshot] = useState<FrameQualityAssessment | null>(null)
  const [guidance, setGuidance] = useState<LiveGuidance | null>(null)
  const [isReady, setIsReady] = useState(false)
  const [analysisTimeMs, setAnalysisTimeMs] = useState<number | null>(null)

  const runningRef = useRef(false)
  const stabilizerRef = useRef(
    new GuidanceStabilizer(qualityConfig.analysis.previewStabilizationCount),
  )

  // Initialize the detector once (M3 §72-73); dispose happens in useCaptureFlow teardown.
  useEffect(() => {
    let cancelled = false
    setDetectorState('LOADING')
    detector
      .initialize()
      .then(() => {
        if (!cancelled) setDetectorState('READY')
      })
      .catch(() => {
        if (!cancelled) setDetectorState('ERROR')
      })
    return () => {
      cancelled = true
    }
  }, [detector])

  const runAnalysis = useCallback(async (): Promise<void> => {
    const video = videoRef.current
    if (!video || runningRef.current) return
    if (video.videoWidth <= 0 || video.videoHeight <= 0) return
    runningRef.current = true
    try {
      const assessment = await analyzeFrame({
        source: video,
        detector,
        frameId: 'live-preview',
        sequence: 0,
        config: qualityConfig,
      })
      if (assessment.disposition === 'ANALYSIS_UNAVAILABLE') return
      setSnapshot(assessment)
      setAnalysisTimeMs(assessment.analysisTimeMs)

      const rawCategory: GuidanceCategory = categoryFromAssessment(
        assessment,
        qualityConfig.guidance.readyScoreThreshold,
      )
      const stabilized = stabilizerRef.current.update(rawCategory)
      if (stabilized) {
        setGuidance(buildLiveGuidance(stabilized))
        setIsReady(stabilized === 'READY')
      }
    } catch {
      // A single preview analysis failure must not crash the camera preview (M3 §75).
    } finally {
      runningRef.current = false
    }
  }, [detector, videoRef])

  // Throttled, backpressured analysis loop (M3 §16-18).
  useEffect(() => {
    if (!enabled) {
      setGuidance(null)
      setIsReady(false)
      stabilizerRef.current.reset()
      return
    }
    if (detectorState !== 'READY') return
    const intervalMs = 1000 / qualityConfig.analysis.previewAnalysisRateHz
    const interval = window.setInterval(() => void runAnalysis(), intervalMs)
    void runAnalysis()
    return () => {
      window.clearInterval(interval)
    }
  }, [enabled, detectorState, runAnalysis])

  return { detectorState, snapshot, guidance, isReady, analysisTimeMs }
}
