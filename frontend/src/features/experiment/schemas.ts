/**
 * M4 experiment result schemas (M4 §128, §130). Mirrors the backend ExperimentResult; the
 * classification/medium/confidence come from the normalized backend contract, never raw provider
 * JSON.
 */

import { z } from 'zod'

export const vlmExperimentResultSchema = z.object({
  experiment: z.boolean(),
  provider: z.string(),
  model: z.string(),
  prompt_version: z.string(),
  schema_version: z.string(),
  frame_strategy: z.string(),
  image_count: z.number(),
  classification: z.string().nullable().optional(),
  attack_medium: z.string().nullable().optional(),
  self_reported_confidence: z.number().nullable().optional(),
  evidence_codes: z.array(z.string()).default([]),
  latency_ms: z.number().nullable().optional(),
  experiment_id: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
})

export type VlmExperimentResult = z.infer<typeof vlmExperimentResultSchema>

export const vlmProviderDescriptorSchema = z.object({
  name: z.string(),
  model: z.string(),
  provider_adapter_version: z.string().optional(),
  max_images: z.number().optional(),
  supports_structured_output: z.boolean().optional(),
  supports_inline_images: z.boolean().optional(),
})

export type VlmProviderDescriptor = z.infer<typeof vlmProviderDescriptorSchema>

export const vlmProvidersSchema = z.object({
  experiment_enabled: z.boolean(),
  environment: z.string().optional(),
  providers: z.array(vlmProviderDescriptorSchema),
  default_provider: z.string().nullable().optional(),
})

/** Transaction creation response (M5.7 §10, §15). */
export const transactionCreateSchema = z.object({
  transaction_id: z.string(),
  status: z.string(),
  capture_artifact: z
    .object({
      relative_path: z.string(),
      content_type: z.string(),
      size_bytes: z.number(),
      sha256: z.string(),
    })
    .optional(),
})
