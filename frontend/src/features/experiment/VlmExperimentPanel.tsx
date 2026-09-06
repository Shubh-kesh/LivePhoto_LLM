/**
 * M4 development experiment panel (M4 §64-69).
 *
 * Rendered only in development builds (CapturePage guards with import.meta.env.DEV). Runs the VLM
 * experiment against the LivePhoto backend (mock provider in E2E) and shows the normalized result.
 * Always labelled "Experimental result — not a banking decision." Never shows "verified"/"approved".
 * No provider keys ever appear; no external provider is called from the browser.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiClientError } from '../../api/client'
import { captureConfig } from '../capture/config/captureConfig'
import { qualityConfig } from '../capture/quality/config/qualityConfig'
import type { CaptureBundle } from '../capture/types/capture'
import type { BundleQualityAssessment } from '../capture/quality/types/quality'
import { evaluateVlmExperiment, getVlmProviders } from './api'
import { selectFramesForStrategy, type ExperimentFrameStrategy } from './frameSelection'
import type { VlmExperimentResult } from './schemas'

interface VlmExperimentPanelProps {
  bundle: CaptureBundle
  quality: BundleQualityAssessment | null
}

const MOCK_BEHAVIORS = [
  'default',
  'screen_replay',
  'live',
  'print',
  'uncertain',
  'quality_failure',
  'timeout',
  'auth',
  'schema',
  'response_error',
]

export function VlmExperimentPanel({ bundle, quality }: VlmExperimentPanelProps) {
  const [providers, setProviders] = useState<string[]>([])
  const [unavailable, setUnavailable] = useState(false)
  const [provider, setProvider] = useState('')
  const [strategy, setStrategy] = useState<ExperimentFrameStrategy>('single-quality-v1')
  const [mockBehavior, setMockBehavior] = useState('default')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<VlmExperimentResult | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getVlmProviders()
      .then((list) => {
        if (cancelled) return
        setProviders(list)
        if (list.length > 0) setProvider(list[0])
      })
      .catch(() => {
        if (!cancelled) setUnavailable(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedFrames = useMemo(
    () => selectFramesForStrategy(bundle, quality, strategy),
    [bundle, quality, strategy],
  )

  const run = useCallback(async () => {
    if (!provider || selectedFrames.length === 0) return
    setRunning(true)
    setErrorMessage(null)
    setResult(null)
    try {
      const outcome = await evaluateVlmExperiment({
        strategy,
        captureConfigVersion: captureConfig.configVersion,
        qualityConfigVersion: qualityConfig.configVersion,
        frameSelectionVersion: strategy,
        provider,
        mockBehavior: provider === 'mock' ? mockBehavior : undefined,
        frames: selectedFrames.map((frame, index) => ({
          blob: frame.blob,
          filename: `frame-${index}.jpg`,
        })),
      })
      setResult(outcome)
    } catch (error) {
      setErrorMessage(
        error instanceof ApiClientError
          ? `${error.code}: ${error.message}`
          : 'The VLM experiment failed.',
      )
    } finally {
      setRunning(false)
    }
  }, [provider, strategy, mockBehavior, selectedFrames])

  if (unavailable) {
    return (
      <section className="vlm-experiment">
        <p>VLM experiment is unavailable in this environment.</p>
      </section>
    )
  }

  const hasFrames = selectedFrames.length > 0

  return (
    <section className="vlm-experiment" aria-labelledby="vlm-experiment-heading">
      <h2 id="vlm-experiment-heading">VLM experiment</h2>
      <p className="vlm-experiment__label">Experimental result — not a banking decision.</p>

      <div className="vlm-experiment__controls">
        <label>
          Provider
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            {providers.length === 0 && <option value="">No providers configured</option>}
            {providers.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Frame strategy
          <select
            value={strategy}
            onChange={(event) => setStrategy(event.target.value as ExperimentFrameStrategy)}
          >
            <option value="single-quality-v1">Single selected frame</option>
            <option value="temporal-triad-v1">Three-frame temporal sample</option>
          </select>
        </label>

        {provider === 'mock' && (
          <label>
            Mock behavior (test builds)
            <select value={mockBehavior} onChange={(event) => setMockBehavior(event.target.value)}>
              {MOCK_BEHAVIORS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {!hasFrames && (
        <p role="alert">
          This strategy needs{' '}
          {strategy === 'temporal-triad-v1' ? '3 eligible frames' : 'an eligible frame'}.
        </p>
      )}

      <button
        type="button"
        className="camera-control"
        onClick={() => void run()}
        disabled={running || !provider || !hasFrames}
      >
        {running ? 'Running experiment…' : 'Run VLM experiment'}
      </button>

      {errorMessage && (
        <p className="vlm-experiment__error" role="alert">
          {errorMessage}
        </p>
      )}

      {result?.error && (
        <p className="vlm-experiment__error" role="alert">
          {result.error}
        </p>
      )}

      {result && (
        <dl className="vlm-experiment__result">
          <div>
            <dt>Provider</dt>
            <dd>{result.provider}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{result.model}</dd>
          </div>
          <div>
            <dt>Frame strategy</dt>
            <dd>{result.frame_strategy}</dd>
          </div>
          <div>
            <dt>VLM classification</dt>
            <dd>{result.classification ?? 'n/a'}</dd>
          </div>
          <div>
            <dt>Attack medium</dt>
            <dd>{result.attack_medium ?? 'n/a'}</dd>
          </div>
          <div>
            <dt>Self-reported confidence</dt>
            <dd>{result.self_reported_confidence ?? 'n/a'}</dd>
          </div>
          <div>
            <dt>Evidence codes</dt>
            <dd>{result.evidence_codes.join(', ') || 'none'}</dd>
          </div>
          <div>
            <dt>Latency</dt>
            <dd>{result.latency_ms ?? 'n/a'} ms</dd>
          </div>
        </dl>
      )}
    </section>
  )
}
