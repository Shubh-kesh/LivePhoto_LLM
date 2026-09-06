/**
 * M4 experiment API client (M4 §128). Browser -> backend multipart only; the browser never talks
 * to external VLM providers and never holds provider keys.
 */

import { apiPostMultipart, apiRequest } from '../../api/client'
import { vlmExperimentResultSchema, vlmProvidersSchema, type VlmExperimentResult } from './schemas'

export interface VlmUploadFrame {
  blob: Blob
  filename: string
}

export interface VlmExperimentInput {
  strategy: 'single-quality-v1' | 'temporal-triad-v1'
  captureConfigVersion: string
  qualityConfigVersion: string
  frameSelectionVersion: string
  provider: string
  mockBehavior?: string
  frames: VlmUploadFrame[]
}

export async function getVlmProviders(): Promise<string[]> {
  const data: unknown = await apiRequest('/api/v1/experiments/vlm/providers')
  return vlmProvidersSchema.parse(data).providers
}

export async function evaluateVlmExperiment(
  input: VlmExperimentInput,
): Promise<VlmExperimentResult> {
  const form = new FormData()
  form.append('strategy', input.strategy)
  form.append('provider', input.provider)
  form.append('capture_config_version', input.captureConfigVersion)
  form.append('quality_config_version', input.qualityConfigVersion)
  form.append('frame_selection_version', input.frameSelectionVersion)
  if (input.mockBehavior) form.append('mock_behavior', input.mockBehavior)
  input.frames.forEach((frame, index) => {
    form.append('frames', frame.blob, frame.filename ?? `frame-${index}.jpg`)
  })

  const data: unknown = await apiPostMultipart('/api/v1/experiments/vlm/evaluate', form)
  return vlmExperimentResultSchema.parse(data)
}
