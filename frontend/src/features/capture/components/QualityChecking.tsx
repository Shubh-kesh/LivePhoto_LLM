/**
 * Quality analysis progress (M3 §61). "Checking photo quality…" — no model jargon, no fake
 * percentage progress.
 */

export function QualityChecking() {
  return (
    <section className="quality-checking" aria-labelledby="quality-checking-heading">
      <h2 id="quality-checking-heading">Checking photo quality…</h2>
      <p role="status">Checking photo quality…</p>
    </section>
  )
}
