import { z } from 'zod'

export const apiErrorDetailSchema = z.object({
  code: z.string(),
  message: z.string(),
  request_id: z.string().optional(),
})

export const apiErrorEnvelopeSchema = z.object({
  error: apiErrorDetailSchema,
})

export type ApiErrorDetail = z.infer<typeof apiErrorDetailSchema>
export type ApiErrorEnvelope = z.infer<typeof apiErrorEnvelopeSchema>
