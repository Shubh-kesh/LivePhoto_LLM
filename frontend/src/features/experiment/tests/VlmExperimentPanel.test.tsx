/**
 * VLM experiment panel tests (M4 §147, M5.6 §84).
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createTransaction, evaluateVlmExperiment, getVlmProviders, processPortrait } from '../api'
import type { CaptureBundle, CaptureFrame } from '../../capture/types/capture'
import type { BundleQualityAssessment } from '../../capture/quality/types/quality'
import { VlmExperimentPanel } from '../VlmExperimentPanel'

vi.mock('../api', () => ({
  getVlmProviders: vi.fn(),
  evaluateVlmExperiment: vi.fn(),
  createTransaction: vi.fn(),
  processPortrait: vi.fn(),
  transactionArtifactUrl: vi.fn(
    (txId: string, type: string) =>
      `http://localhost:8000/api/v1/transactions/${txId}/artifacts/${type}`,
  ),
}))

const mockedProviders = vi.mocked(getVlmProviders)
const mockedEvaluate = vi.mocked(evaluateVlmExperiment)
const mockedCreateTransaction = vi.mocked(createTransaction)
const mockedProcessPortrait = vi.mocked(processPortrait)

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

function bundle(): CaptureBundle {
  const frames = ['a', 'b', 'c', 'd', 'e'].map((id, index) => frame(id, index))
  return {
    captureId: 'capture-1',
    createdAt: '2026-01-01T00:00:00Z',
    captureConfigVersion: 'capture-v1',
    camera: { facingMode: 'user' },
    frames,
    representativeFrameId: 'c',
  }
}

function quality(): BundleQualityAssessment {
  return {
    captureId: 'capture-1',
    captureConfigVersion: 'capture-v1',
    qualityConfigVersion: 'quality-v1',
    frames: [],
    eligibleFrameIds: ['a', 'b', 'c', 'd', 'e'],
    selectedFrameId: 'c',
    selectionAlgorithmVersion: 'frame-ranking-v2',
    disposition: 'QUALITY_READY',
    reasonCodes: [],
    totalAnalysisTimeMs: 1,
  }
}

function openPanel(): void {
  fireEvent.click(screen.getByText('VLM test'))
}

describe('VlmExperimentPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedProviders.mockResolvedValue({
      experimentEnabled: true,
      defaultProvider: 'mock',
      providers: [{ name: 'mock', model: 'mock-vision-v1' }],
    })
    mockedCreateTransaction.mockResolvedValue({
      transactionId: 'tx-default',
      status: 'CAPTURE_READY',
    })
    mockedProcessPortrait.mockResolvedValue({ status: 'SUCCESS' })
  })

  it('is collapsed by default and shows the UAT-only note', async () => {
    const { container } = render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    expect(screen.getByText('VLM test')).toBeInTheDocument()
    expect(screen.getByText('Experimental — UAT only')).toBeInTheDocument()
    // Collapsed by default: the panel details are closed until the tester expands them.
    expect((container.querySelector('.vlm-experiment') as HTMLDetailsElement | null)?.open).toBe(
      false,
    )
  })

  it('shows the experimental label and never "verified" wording', async () => {
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    expect(
      await screen.findByText('Experimental result — not a banking decision.'),
    ).toBeInTheDocument()
    const text = document.body.textContent ?? ''
    expect(text.toLowerCase()).not.toContain('verified')
    expect(text.toLowerCase()).not.toContain('approved')
  })

  it('shows a safe unavailable message when providers are not configured', async () => {
    mockedProviders.mockRejectedValue(new Error('disabled'))
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    expect(
      await screen.findByText('VLM experiment is unavailable in this environment.'),
    ).toBeInTheDocument()
  })

  it('runs a single-frame experiment and shows the normalized result', async () => {
    mockedEvaluate.mockResolvedValue({
      experiment: true,
      provider: 'mock',
      model: 'mock-vision-v1',
      prompt_version: 'vlm-passive-v1',
      schema_version: 'vlm-result-v1',
      frame_strategy: 'single-quality-v1',
      image_count: 1,
      classification: 'SCREEN_REPLAY',
      attack_medium: 'MOBILE_SCREEN',
      self_reported_confidence: 0.86,
      evidence_codes: ['DEVICE_BORDER_VISIBLE'],
      latency_ms: 120,
    })
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    await screen.findByText('Experimental result — not a banking decision.')

    fireEvent.click(screen.getByRole('button', { name: 'Run VLM test' }))
    await waitFor(() => expect(mockedEvaluate).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('SCREEN_REPLAY')).toBeInTheDocument()
    expect(screen.getAllByText('mock-vision-v1').length).toBeGreaterThan(0)
    expect(screen.getByText('DEVICE_BORDER_VISIBLE')).toBeInTheDocument()
  })

  it('shows a safe error when the provider fails', async () => {
    const { ApiClientError } = await import('../../../api/client')
    mockedEvaluate.mockRejectedValue(
      new ApiClientError('PROVIDER_TIMEOUT', 'provider request timed out', 503, null),
    )
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    await screen.findByText('Experimental result — not a banking decision.')

    fireEvent.click(screen.getByRole('button', { name: 'Run VLM test' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('PROVIDER_TIMEOUT')
  })

  it('allows choosing the triad strategy', async () => {
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    await screen.findByText('Experimental result — not a banking decision.')
    fireEvent.change(screen.getByLabelText('Frame strategy'), {
      target: { value: 'temporal-triad-v1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Run VLM test' }))
    await waitFor(() => expect(mockedEvaluate).toHaveBeenCalledTimes(1))
    expect(mockedEvaluate.mock.calls[0][0].strategy).toBe('temporal-triad-v1')
    expect(mockedEvaluate.mock.calls[0][0].frames).toHaveLength(3)
  })

  it('LIVE result triggers portrait processing and shows the final photo (M5.7 §66-68)', async () => {
    mockedEvaluate.mockResolvedValue({
      experiment: true,
      provider: 'mock',
      model: 'mock-vision-v1',
      prompt_version: 'vlm-passive-v1',
      schema_version: 'vlm-result-v1',
      frame_strategy: 'single-quality-v1',
      image_count: 1,
      classification: 'LIVE',
      attack_medium: 'NONE',
      self_reported_confidence: 0.95,
      evidence_codes: [],
      latency_ms: 120,
      experiment_id: 'exp-1',
    })
    mockedCreateTransaction.mockResolvedValue({ transactionId: 'tx-1', status: 'CAPTURE_READY' })
    mockedProcessPortrait.mockResolvedValue({ status: 'SUCCESS' })
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    await screen.findByText('Experimental result — not a banking decision.')

    fireEvent.click(screen.getByRole('button', { name: 'Run VLM test' }))
    expect(await screen.findByTestId('processed-portrait')).toBeInTheDocument()
    expect(mockedCreateTransaction).toHaveBeenCalledTimes(1)
    expect(mockedProcessPortrait).toHaveBeenCalledTimes(1)
    const img = screen.getByRole('img', { name: 'Processed portrait preview' })
    expect(img.getAttribute('src')).toContain('/artifacts/PROCESSED_PORTRAIT')
    // Not labelled as verification.
    const body = document.body.textContent ?? ''
    expect(body.toLowerCase()).not.toContain('verified')
  })

  it('non-LIVE result does NOT trigger portrait processing (M5.7 §66)', async () => {
    mockedEvaluate.mockResolvedValue({
      experiment: true,
      provider: 'mock',
      model: 'mock-vision-v1',
      prompt_version: 'vlm-passive-v1',
      schema_version: 'vlm-result-v1',
      frame_strategy: 'single-quality-v1',
      image_count: 1,
      classification: 'SCREEN_REPLAY',
      attack_medium: 'MOBILE_SCREEN',
      self_reported_confidence: 0.86,
      evidence_codes: [],
      latency_ms: 120,
    })
    mockedCreateTransaction.mockResolvedValue({ transactionId: 'tx-2', status: 'CAPTURE_READY' })
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    await screen.findByText('Experimental result — not a banking decision.')
    fireEvent.click(screen.getByRole('button', { name: 'Run VLM test' }))
    await waitFor(() => expect(mockedEvaluate).toHaveBeenCalledTimes(1))
    expect(screen.queryByTestId('processed-portrait')).not.toBeInTheDocument()
    expect(screen.queryByText('Preparing final photo…')).not.toBeInTheDocument()
    expect(mockedProcessPortrait).not.toHaveBeenCalled()
  })

  it('portrait processing failure shows a customer-safe technical error (M5.7 §45-46)', async () => {
    mockedEvaluate.mockResolvedValue({
      experiment: true,
      provider: 'mock',
      model: 'mock-vision-v1',
      prompt_version: 'vlm-passive-v1',
      schema_version: 'vlm-result-v1',
      frame_strategy: 'single-quality-v1',
      image_count: 1,
      classification: 'LIVE',
      attack_medium: 'NONE',
      self_reported_confidence: 0.95,
      evidence_codes: [],
      latency_ms: 120,
      experiment_id: 'exp-3',
    })
    mockedCreateTransaction.mockResolvedValue({ transactionId: 'tx-3', status: 'CAPTURE_READY' })
    mockedProcessPortrait.mockRejectedValue(new Error('matting failed'))
    render(<VlmExperimentPanel bundle={bundle()} quality={quality()} />)
    openPanel()
    await screen.findByText('Experimental result — not a banking decision.')
    fireEvent.click(screen.getByRole('button', { name: 'Run VLM test' }))
    expect(await screen.findByTestId('portrait-error')).toHaveTextContent(
      "We couldn't prepare your photo. Please try again.",
    )
    // No matting/segmentation jargon on the customer path.
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/matting|segmentation|ONNX|alpha/i)
    expect(screen.queryByTestId('processed-portrait')).not.toBeInTheDocument()
  })
})
