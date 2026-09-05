/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  /** Test/E2E builds only: selects the deterministic stub face detector (M3 §100-102). */
  readonly VITE_FACE_PROVIDER?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
