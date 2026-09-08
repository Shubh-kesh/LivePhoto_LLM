/**
 * M5.8 integration browser API client. Same-origin relative paths with credentials (cookies) and
 * the session-bound CSRF token. The browser never sends Base64; images upload as multipart.
 */

import { apiPostJson, apiPostMultipart, apiRequest } from '../../api/client'
import { browserSessionSchema, submitResultSchema, type BrowserSessionState } from './schemas'

export async function fetchBrowserSession(): Promise<BrowserSessionState> {
  const data: unknown = await apiRequest('/api/v1/browser/session')
  return browserSessionSchema.parse(data)
}

/** Register a frontend-only quality failure for a capture attempt (M5.8 §13). */
export async function registerAttempt(attemptId: string, reasonCode: string): Promise<unknown> {
  const form = new FormData()
  form.append('attempt_id', attemptId)
  form.append('result', 'QUALITY_RETRY')
  form.append('reason_code', reasonCode)
  return apiPostMultipart('/api/v1/browser/attempts', form)
}

/** Upload a selected capture frame for an attempt (M5.8 §13). */
export async function uploadCapture(
  attemptId: string,
  image: Blob,
  filename = 'selected-original.jpg',
): Promise<unknown> {
  const form = new FormData()
  form.append('attempt_id', attemptId)
  form.append('selected_image', image, filename)
  return apiPostMultipart('/api/v1/browser/capture', form, 20_000)
}

/** Trigger backend portrait processing (requires canonical PASS). */
export async function triggerPortrait(): Promise<unknown> {
  const form = new FormData()
  return apiPostMultipart('/api/v1/browser/portrait', form, 60_000)
}

/** Test-only canonical PASS writer (local/test/dev only; enabled via env). */
export async function writeTestDecision(): Promise<unknown> {
  return apiPostJson('/api/v1/dev/test-decision', {})
}

export async function submitForConsumer(): Promise<string> {
  const data: unknown = await apiPostJson('/api/v1/browser/submit', {})
  return submitResultSchema.parse(data).redirect_url
}

export function browserPortraitUrl(): string {
  return '/api/v1/browser/portrait'
}
