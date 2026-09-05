/**
 * Camera introduction screen (M2 §7, §60). Camera permission is never requested on page load;
 * it follows the explicit "Start camera" action.
 */

interface CameraIntroductionProps {
  onStart: () => void
  pending: boolean
}

export function CameraIntroduction({ onStart, pending }: CameraIntroductionProps) {
  return (
    <section className="capture-intro" aria-labelledby="capture-intro-heading">
      <h2 id="capture-intro-heading">We need access to your camera</h2>
      <p>We need access to your camera to capture your photo.</p>
      <button type="button" className="primary-action" onClick={onStart} disabled={pending}>
        {pending ? 'Requesting camera access…' : 'Start camera'}
      </button>
      <p className="privacy-note">Your camera is used to capture your photo.</p>
    </section>
  )
}
