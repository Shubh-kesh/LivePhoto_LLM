import { z } from 'zod'

const browserPolicyEntrySchema = z.object({
  minimum_major: z.number().int().positive(),
  enabled: z.boolean(),
})

/** Mirrors the backend /api/v1/info browser_policy contract (backend/app/core/browser_policy.py). */
export const browserPolicySchema = z.object({
  policy_version: z.string(),
  browsers: z.object({
    chrome: browserPolicyEntrySchema,
    edge: browserPolicyEntrySchema,
    firefox: browserPolicyEntrySchema,
    safari: browserPolicyEntrySchema,
    ios_safari: browserPolicyEntrySchema,
    android_chrome: browserPolicyEntrySchema,
  }),
})

export type BrowserPolicy = z.infer<typeof browserPolicySchema>

/** Mirrors the backend /api/v1/info contract (see backend/tests/contract/test_info_shape.py). */
export const infoResponseSchema = z.object({
  name: z.string(),
  version: z.string(),
  environment: z.string(),
  browser_policy: browserPolicySchema.nullable().optional(),
})

export type InfoResponse = z.infer<typeof infoResponseSchema>
