/**
 * M5.8 API client tests: same-origin credentials + CSRF header on browser mutations.
 */

import { afterEach, describe, expect, it } from 'vitest'

import { readCsrfToken } from '../../../api/client'

describe('readCsrfToken (M5.8 §11)', () => {
  afterEach(() => {
    document.cookie = 'lp_csrf=; Max-Age=0; path=/'
  })

  it('reads lp_csrf from document.cookie', () => {
    document.cookie = 'lp_csrf=abc123'
    expect(readCsrfToken()).toBe('abc123')
  })

  it('returns empty string when lp_csrf is absent', () => {
    expect(readCsrfToken()).toBe('')
  })
})
