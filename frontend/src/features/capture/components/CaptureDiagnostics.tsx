/**
 * Development-only capture diagnostics (M2 §68-69, §84, §95).
 *
 * Shows non-sensitive timing/size/facing data. Never shows deviceId, groupId, Base64 images, raw
 * blob contents or full DOMException messages. Never rendered in production builds.
 */

import type { CaptureDiagnostics } from '../types/capture'

export function CaptureDiagnostics({ diagnostics }: { diagnostics: CaptureDiagnostics | null }) {
  if (import.meta.env.PROD) return null
  if (!diagnostics) return null

  return (
    <details className="capture-diagnostics" data-testid="capture-diagnostics">
      <summary>Capture diagnostics (development)</summary>
      <dl>
        <div>
          <dt>Camera settings</dt>
          <dd>
            {diagnostics.width ?? '?'}x{diagnostics.height ?? '?'}
            {diagnostics.frameRate ? ` @ ${diagnostics.frameRate}fps` : ''}
            {diagnostics.facingMode ? ` · ${diagnostics.facingMode}` : ''}
          </dd>
        </div>
        <div>
          <dt>Frame scheduler</dt>
          <dd>{diagnostics.scheduler ?? 'n/a'}</dd>
        </div>
        <div>
          <dt>Captured frames</dt>
          <dd>{diagnostics.frameCount}</dd>
        </div>
        <div>
          <dt>Total burst bytes</dt>
          <dd>{diagnostics.totalBytes}</dd>
        </div>
        <div>
          <dt>Camera start</dt>
          <dd>
            {diagnostics.cameraStartMs !== null
              ? `${diagnostics.cameraStartMs.toFixed(0)} ms`
              : 'n/a'}
          </dd>
        </div>
        <div>
          <dt>Burst duration</dt>
          <dd>
            {diagnostics.burstDurationMs !== null
              ? `${diagnostics.burstDurationMs.toFixed(0)} ms`
              : 'n/a'}
          </dd>
        </div>
        <div>
          <dt>Total flow</dt>
          <dd>
            {diagnostics.totalFlowMs !== null ? `${diagnostics.totalFlowMs.toFixed(0)} ms` : 'n/a'}
          </dd>
        </div>
      </dl>
    </details>
  )
}
