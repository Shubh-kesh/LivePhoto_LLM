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
import { Button } from '../../design-system'
import { captureConfig } from '../capture/config/captureConfig'
import { qualityConfig } from '../capture/quality/config/qualityConfig'
import type { CaptureBundle } from '../capture/types/capture'
import type { BundleQualityAssessment } from '../capture/quality/types/quality'
import {
  createTransaction,
  evaluateVlmExperiment,
  getVlmProviders,
  processPortrait,
  transactionArtifactUrl,
} from './api'
import { selectFramesForStrategy, type ExperimentFrameStrategy } from './frameSelection'
import type { VlmExperimentResult, VlmProviderDescriptor } from './schemas'
import './vlm-panel.css'

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
  const [providers, setProviders] = useState<VlmProviderDescriptor[]>([])
  const [unavailable, setUnavailable] = useState(false)
  const [provider, setProvider] = useState('')
  const [strategy, setStrategy] = useState<ExperimentFrameStrategy>('single-quality-v1')
  const [mockBehavior, setMockBehavior] = useState('default')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<VlmExperimentResult | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [transactionId, setTransactionId] = useState<string | null>(null)
  const [portraitState, setPortraitState] = useState<'idle' | 'processing' | 'ready' | 'error'>(
    'idle',
  )
  const [processedUrl, setProcessedUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getVlmProviders()
      .then(({ providers: list, defaultProvider }) => {
        if (cancelled) return
        setProviders(list)
        if (list.length > 0) setProvider(defaultProvider ?? list[0].name)
      })
      .catch(() => {
        if (!cancelled) setUnavailable(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedProvider = providers.find((descriptor) => descriptor.name === provider) ?? null

  const selectedFrames = useMemo(
    () => selectFramesForStrategy(bundle, quality, strategy),
    [bundle, quality, strategy],
  )

  // The representative capture is the M5.7 selected-original source (M5.7 §17).
  const representativeFrame = useMemo(
    () =>
      bundle.frames.find((frame) => frame.id === bundle.representativeFrameId) ??
      bundle.frames[0] ??
      null,
    [bundle],
  )

  const faceBoxNormalized = useMemo(() => {
    if (!quality?.selectedFrameId) return undefined
    const frame = quality.frames.find((f) => f.frameId === quality.selectedFrameId)
    const box = frame?.face.normalizedBoundingBox
    if (!box) return undefined
    return `${box.x},${box.y},${box.width},${box.height}`
  }, [quality])

  const run = useCallback(async () => {
    if (!provider || selectedFrames.length === 0) return
    setRunning(true)
    setErrorMessage(null)
    setResult(null)
    setPortraitState('idle')
    setProcessedUrl(null)
    try {
      // Transaction folder is created FIRST; every artifact lives under it (M5.7 §2).
      let txId = transactionId
      if (!txId && representativeFrame) {
        const created = await createTransaction(
          representativeFrame.blob,
          captureConfig.configVersion,
          qualityConfig.configVersion,
          faceBoxNormalized,
        )
        txId = created.transactionId
        setTransactionId(txId)
      }
      const outcome = await evaluateVlmExperiment({
        strategy,
        captureConfigVersion: captureConfig.configVersion,
        qualityConfigVersion: qualityConfig.configVersion,
        frameSelectionVersion: strategy,
        provider,
        mockBehavior: provider === 'mock' ? mockBehavior : undefined,
        transactionId: txId ?? undefined,
        frames: selectedFrames.map((frame, index) => ({
          blob: frame.blob,
          filename: `frame-${index}.jpg`,
        })),
      })
      setResult(outcome)

      // Experimental LIVE trigger for the portrait pipeline (M5.7 §21). Diagnostic only.
      if (outcome.classification === 'LIVE' && txId) {
        setPortraitState('processing')
        try {
          await processPortrait(txId, faceBoxNormalized)
          setProcessedUrl(transactionArtifactUrl(txId, 'PROCESSED_PORTRAIT'))
          setPortraitState('ready')
        } catch {
          setPortraitState('error')
        }
      }
    } catch (error) {
      setErrorMessage(
        error instanceof ApiClientError
          ? `${error.code}: ${error.message}`
          : 'The VLM experiment failed.',
      )
    } finally {
      setRunning(false)
    }
  }, [
    provider,
    strategy,
    mockBehavior,
    selectedFrames,
    transactionId,
    representativeFrame,
    faceBoxNormalized,
  ])

  if (unavailable) {
    return (
      <section className="vlm-experiment">
        <p>VLM experiment is unavailable in this environment.</p>
      </section>
    )
  }

  const hasFrames = selectedFrames.length > 0

  return (
    <details className="vlm-experiment" data-testid="vlm-experiment" aria-label="VLM test">
      <summary className="vlm-experiment__summary">
        <span>VLM test</span>
        <span className="vlm-experiment__uat-note">Experimental — UAT only</span>
      </summary>

      <p className="vlm-experiment__label">Experimental result — not a banking decision.</p>

      <div className="vlm-experiment__controls">
        <label>
          Provider
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            {providers.length === 0 && <option value="">No providers configured</option>}
            {providers.map((descriptor) => (
              <option key={descriptor.name} value={descriptor.name}>
                {descriptor.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Model
          <span className="vlm-experiment__model">{selectedProvider?.model ?? '—'}</span>
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

      <Button
        type="button"
        className="vlm-experiment__run"
        onClick={() => void run()}
        disabled={running || !provider || !hasFrames}
      >
        {running ? 'Running experiment…' : 'Run VLM test'}
      </Button>

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
          <div>
            <dt>Request ID</dt>
            <dd>{result.experiment_id ?? 'n/a'}</dd>
          </div>
        </dl>
      )}

      {/* M5.7: experimental LIVE trigger — processed portrait preview (diagnostic only). */}
      {portraitState === 'processing' && (
        <p
          className="vlm-experiment__portrait-status"
          role="status"
          data-testid="portrait-processing"
        >
          Preparing final photo…
        </p>
      )}
      {portraitState === 'ready' && processedUrl && (
        <section className="vlm-experiment__portrait" data-testid="processed-portrait">
          <h3 className="vlm-experiment__portrait-title">Final photo</h3>
          <img
            className="vlm-experiment__portrait-image"
            src={processedUrl}
            alt="Processed portrait preview"
          />
        </section>
      )}
      {portraitState === 'error' && (
        <p className="vlm-experiment__error" role="alert" data-testid="portrait-error">
          We couldn't prepare your photo. Please try again.
        </p>
      )}
    </details>
  )
}
