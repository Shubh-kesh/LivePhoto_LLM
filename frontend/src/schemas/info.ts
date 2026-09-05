import { z } from 'zod'

/** Mirrors the backend /api/v1/info contract (see backend/tests/contract/test_info_shape.py). */
export const infoResponseSchema = z.object({
  name: z.string(),
  version: z.string(),
  environment: z.string(),
})

export type InfoResponse = z.infer<typeof infoResponseSchema>
