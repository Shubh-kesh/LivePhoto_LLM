import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError, apiRequest } from '../api/client'

function fakeResponse({
  ok,
  status,
  body,
  headers = {},
}: {
  ok: boolean
  status: number
  body: unknown
  headers?: Record<string, string>
}): Response {
  return {
    ok,
    status,
    headers: { get: (name: string) => headers[name.toLowerCase()] ?? null },
    json: async () => body,
  } as unknown as Response
}

describe('apiRequest', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns parsed JSON on success and captures the request id', async () => {
    vi.mocked(fetch).mockResolvedValue(
      fakeResponse({
        ok: true,
        status: 200,
        body: { name: 'LivePhoto', version: '0.1.0', environment: 'test' },
        headers: { 'x-request-id': 'req-123' },
      }),
    )
    const result = await apiRequest<{ name: string }>('/api/v1/info')
    expect(result).toEqual({ name: 'LivePhoto', version: '0.1.0', environment: 'test' })
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/info'),
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('throws ApiClientError with the server error envelope', async () => {
    vi.mocked(fetch).mockResolvedValue(
      fakeResponse({
        ok: false,
        status: 422,
        body: {
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Request validation failed',
            request_id: 'r1',
          },
        },
      }),
    )
    const promise = apiRequest('/api/v1/info')
    await expect(promise).rejects.toBeInstanceOf(ApiClientError)
    await expect(promise).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      message: 'Request validation failed',
      status: 422,
    })
  })

  it('falls back to a generic error for non-envelope failures', async () => {
    vi.mocked(fetch).mockResolvedValue(
      fakeResponse({ ok: false, status: 500, body: { oops: true } }),
    )
    const promise = apiRequest('/api/v1/info')
    await expect(promise).rejects.toMatchObject({
      code: 'UNKNOWN_ERROR',
      status: 500,
    })
  })

  it('maps network failures to a safe ApiClientError', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
    const promise = apiRequest('/api/v1/info')
    await expect(promise).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      status: 0,
    })
  })
})
