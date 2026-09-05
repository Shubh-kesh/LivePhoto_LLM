/** Object URL helpers (M2 §47). Every created URL must be paired with a revoke. */

export function createObjectUrl(blob: Blob): string {
  return URL.createObjectURL(blob)
}

export function revokeObjectUrl(url: string | null): void {
  if (url) {
    URL.revokeObjectURL(url)
  }
}
