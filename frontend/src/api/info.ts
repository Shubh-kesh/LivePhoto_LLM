import { apiRequest } from './client'
import { infoResponseSchema, type InfoResponse } from '../schemas/info'

export async function getInfo(): Promise<InfoResponse> {
  const data: unknown = await apiRequest('/api/v1/info')
  return infoResponseSchema.parse(data)
}
