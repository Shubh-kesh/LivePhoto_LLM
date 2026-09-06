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
  error: z.string().nullable().optional(),
})

export type VlmExperimentResult = z.infer<typeof vlmExperimentResultSchema>

export const vlmProvidersSchema = z.object({
  providers: z.array(z.string()),
})
