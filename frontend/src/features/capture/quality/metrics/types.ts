/** Shared analysis-buffer types (M3 §28). */

export interface AnalysisBuffer {
  width: number
  height: number
  /** Grayscale luminance per pixel in the normalized analysis representation (0..1). */
  gray: Float32Array
}
