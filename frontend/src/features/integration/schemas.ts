/**
 * M5.8 integration browser API schemas (Zod). Mirrors the backend browser-session/status payloads.
 */

import { z } from 'zod'

export const browserSessionSchema = z.object({
  state: z.enum(['active', 'completed', 'invalid', 'expired', 'attempt_limit']),
  submission_ready: z.boolean().optional(),
  attempt_count: z.number().optional(),
  max_attempts: z.number().optional(),
  reason_codes: z.array(z.string()).optional(),
  terminal_state: z.string().nullable().optional(),
})

export type BrowserSessionState = z.infer<typeof browserSessionSchema>

export const attemptResultSchema = z.object({
  attempt_count: z.number(),
  max_attempts: z.number(),
  warning: z.boolean(),
  terminal: z.boolean(),
  status: z.string().nullable().optional(),
})

export const submitResultSchema = z.object({
  redirect_url: z.string(),
})

export const decisionResultSchema = z.object({
  decision_id: z.string(),
  outcome: z.string(),
  submission_ready: z.boolean(),
})
