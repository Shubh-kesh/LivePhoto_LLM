/**
 * M4 experiment API client (M4 §128). Browser -> backend multipart only; the browser never talks
 * to external VLM providers and never holds provider keys.
 */

import { apiPostMultipart, apiRequest } from '../../api/client'
import { API_BASE_URL } from '../../lib/env'
import {
  transactionCreateSchema,
  vlmExperimentResultSchema,
  vlmProvidersSchema,
  type VlmExperimentResult,
  type VlmProviderDescriptor,
} from './schemas'

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
  transactionId?: string
  frames: VlmUploadFrame[]
}

export async function getVlmProviders(): Promise<{
  experimentEnabled: boolean
  defaultProvider: string | null
  providers: VlmProviderDescriptor[]
}> {
  const data: unknown = await apiRequest('/api/v1/experiments/vlm/providers')
  const parsed = vlmProvidersSchema.parse(data)
  return {
    experimentEnabled: parsed.experiment_enabled,
    defaultProvider: parsed.default_provider ?? null,
    providers: parsed.providers,
  }
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
  if (input.transactionId) form.append('transaction_id', input.transactionId)
  input.frames.forEach((frame, index) => {
    form.append('frames', frame.blob, frame.filename ?? `frame-${index}.jpg`)
  })

  const data: unknown = await apiPostMultipart('/api/v1/experiments/vlm/evaluate', form)
  return vlmExperimentResultSchema.parse(data)
}

export interface TransactionCreateResult {
  transactionId: string
  status: string
}

/** Create a transaction folder and persist the selected original capture (M5.7 §2, §17). */
export async function createTransaction(
  image: Blob,
  captureConfigVersion: string,
  qualityConfigVersion: string,
): Promise<TransactionCreateResult> {
  const form = new FormData()
  form.append('image', image, 'selected-original.jpg')
  form.append('capture_config_version', captureConfigVersion)
  form.append('quality_config_version', qualityConfigVersion)
  const data: unknown = await apiPostMultipart('/api/v1/transactions', form, 15_000)
  const parsed = transactionCreateSchema.parse(data)
  return { transactionId: parsed.transaction_id, status: parsed.status }
}

/** Trigger backend portrait processing for a transaction with a LIVE VLM result (M5.7 §21). */
export async function processPortrait(
  transactionId: string,
  faceBoxNormalized?: string,
): Promise<unknown> {
  const form = new FormData()
  if (faceBoxNormalized) form.append('face_box', faceBoxNormalized)
  return apiPostMultipart(`/api/v1/transactions/${transactionId}/portrait`, form, 60_000)
}

/** Server-authoritative liveness of a stored capture (configured VLM_PROVIDER; /capture streamlined). */
export interface TransactionLivenessResult {
  classification: string | null
  outcome: string
  portrait_allowed: boolean
  /** Safe retry reason codes (e.g. MULTIPLE_FACES), never raw VLM/provider output. */
  reason_codes?: string[]
}

export async function evaluateTransactionLiveness(
  transactionId: string,
  attemptId?: string,
): Promise<TransactionLivenessResult> {
  const form = new FormData()
  if (attemptId) form.append('attempt_id', attemptId)
  const data: unknown = await apiPostMultipart(
    `/api/v1/transactions/${transactionId}/liveness`,
    form,
    60_000,
  )
  return data as TransactionLivenessResult
}

/** Controlled artifact URL for display (never an absolute server filesystem path) (M5.7 §62). */
export function transactionArtifactUrl(transactionId: string, artifactType: string): string {
  return `${API_BASE_URL}/api/v1/transactions/${transactionId}/artifacts/${artifactType}`
}
