import { apiErrorEnvelopeSchema } from '../schemas/error'
import type { JsonRecord } from '../types/api'
import { API_BASE_URL } from '../lib/env'

export class ApiClientError extends Error {
  readonly code: string
  readonly status: number
  readonly requestId: string | null

  constructor(code: string, message: string, status: number, requestId: string | null) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.status = status
    this.requestId = requestId
  }
}

interface ApiRequestOptions {
  timeoutMs?: number
  headers?: Record<string, string>
}

const DEFAULT_TIMEOUT_MS = 10_000

/**
 * Minimal typed HTTP client. Centralizes base URL, request ID capture, safe error parsing and
 * timeouts. Foundation calls only (M1 §40).
 */
export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const response = await request(path, {
    method: 'GET',
    headers: options.headers,
    timeoutMs: options.timeoutMs,
  })
  return (await response.json()) as T
}

/** Multipart POST (M4 §12): image bytes are sent as form data, never JSON Base64. */
export async function apiPostMultipart(
  path: string,
  body: FormData,
  timeoutMs = 15_000,
): Promise<unknown> {
  const response = await request(path, { method: 'POST', body, timeoutMs })
  return (await response.json()) as unknown
}

async function request(
  path: string,
  options: {
    method: string
    headers?: Record<string, string>
    body?: BodyInit
    timeoutMs?: number
  },
): Promise<Response> {
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method,
      headers: { Accept: 'application/json', ...(options.headers ?? {}) },
      body: options.body,
      signal: controller.signal,
    })
  } catch {
    throw new ApiClientError('NETWORK_ERROR', 'Unable to reach the service', 0, null)
  } finally {
    clearTimeout(timer)
  }

  const requestId = response.headers.get('x-request-id')
  if (!response.ok) {
    throw await parseErrorResponse(response, requestId)
  }
  return response
}

async function parseErrorResponse(
  response: Response,
  requestId: string | null,
): Promise<ApiClientError> {
  try {
    const data = (await response.json()) as JsonRecord
    const parsed = apiErrorEnvelopeSchema.safeParse(data)
    if (parsed.success) {
      return new ApiClientError(
        parsed.data.error.code,
        parsed.data.error.message,
        response.status,
        requestId,
      )
    }
  } catch {
    // Non-JSON or unexpected body: fall through to a generic error.
  }
  return new ApiClientError('UNKNOWN_ERROR', 'Request failed', response.status, requestId)
}
