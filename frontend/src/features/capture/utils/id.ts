/** Local identifier helper (M2 §33). Never confused with session/transaction/decision IDs. */

let fallbackCounter = 0

export function randomId(): string {
  const cryptoObj = typeof crypto !== 'undefined' ? crypto : undefined
  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') {
    return cryptoObj.randomUUID()
  }
  fallbackCounter += 1
  return `local-${Date.now().toString(36)}-${fallbackCounter.toString(36)}`
}
