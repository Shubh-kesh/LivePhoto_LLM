/**
 * Capture preview (M2 §42-45, §47, §97). Uses the representative Blob's object URL directly;
 * no lossy re-encode is created just for display.
 */

interface CapturePreviewProps {
  previewUrl: string
  onRetake: () => void
  onConfirm: () => void
}

export function CapturePreview({ previewUrl, onRetake, onConfirm }: CapturePreviewProps) {
  return (
    <section className="capture-preview" aria-labelledby="capture-preview-heading">
      <h2 id="capture-preview-heading">Preview your photo</h2>
      <img className="capture-preview__image" src={previewUrl} alt="Your captured photo preview" />
      <div className="capture-preview__actions">
        <button type="button" className="camera-control" onClick={onRetake}>
          Retake photo
        </button>
        <button type="button" className="primary-action" onClick={onConfirm}>
          Use photo
        </button>
      </div>
    </section>
  )
}
