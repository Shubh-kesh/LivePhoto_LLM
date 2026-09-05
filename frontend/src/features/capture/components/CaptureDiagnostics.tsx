/**
 * Development-only capture diagnostics (M2 §68-69, §84, §95 + M3 §70-71).
 *
 * Shows non-sensitive timing/size/facing/quality data. Never shows deviceId, groupId, Base64
 * images, raw blobs, canvas pixel data or full DOMException messages. Never rendered in production
 * builds.
 */

import type { CaptureDiagnostics as CaptureDiagnosticsData } from '../types/capture'
import type { BundleQualityAssessment, FrameQualityAssessment } from '../quality/types/quality'

interface QualityDiagnosticsData {
  live?: FrameQualityAssessment | null
  bundle?: BundleQualityAssessment | null
}

export function CaptureDiagnostics({
  diagnostics,
  quality,
}: {
  diagnostics: CaptureDiagnosticsData | null
  quality?: QualityDiagnosticsData
}) {
  if (import.meta.env.PROD) return null
  if (!diagnostics && !quality?.live && !quality?.bundle) return null

  return (
    <details className="capture-diagnostics" data-testid="capture-diagnostics">
      <summary>Capture diagnostics (development)</summary>
      <dl>
        {diagnostics && (
          <>
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
                {diagnostics.totalFlowMs !== null
                  ? `${diagnostics.totalFlowMs.toFixed(0)} ms`
                  : 'n/a'}
              </dd>
            </div>
          </>
        )}

        {quality?.live && <QualityMetricRows label="Live frame" assessment={quality.live} />}
        {quality?.bundle && (
          <>
            <div>
              <dt>Bundle disposition</dt>
              <dd>{quality.bundle.disposition}</dd>
            </div>
            <div>
              <dt>Eligible frames</dt>
              <dd>
                {quality.bundle.eligibleFrameIds.length}/{quality.bundle.frames.length}
              </dd>
            </div>
            <div>
              <dt>Selected frame</dt>
              <dd>{quality.bundle.selectedFrameId ?? 'n/a'}</dd>
            </div>
            <div>
              <dt>Bundle analysis</dt>
              <dd>{quality.bundle.totalAnalysisTimeMs.toFixed(0)} ms</dd>
            </div>
            <div>
              <dt>Quality config</dt>
              <dd>{quality.bundle.qualityConfigVersion}</dd>
            </div>
          </>
        )}
      </dl>
    </details>
  )
}

function QualityMetricRows({
  label,
  assessment,
}: {
  label: string
  assessment: FrameQualityAssessment
}) {
  const a = assessment
  return (
    <>
      <div>
        <dt>{label} · face</dt>
        <dd>
          count={a.face.count}
          {a.face.detectionConfidence !== undefined
            ? ` conf=${a.face.detectionConfidence.toFixed(2)}`
            : ''}
          {a.face.coverageRatio !== undefined ? ` coverage=${a.face.coverageRatio.toFixed(2)}` : ''}
          {a.face.centerOffset !== undefined
            ? ` center=${a.face.centerOffset.distance.toFixed(2)}`
            : ''}
        </dd>
      </div>
      <div>
        <dt>{label} · exposure</dt>
        <dd>
          mean={a.exposure.meanLuminance.toFixed(2)} dark={a.exposure.darkPixelRatio.toFixed(2)}{' '}
          bright={a.exposure.brightPixelRatio.toFixed(2)}
        </dd>
      </div>
      <div>
        <dt>{label} · contrast / sharpness</dt>
        <dd>
          contrast={a.contrast.rawValue.toFixed(3)} sharpness={a.sharpness.rawValue.toFixed(1)}
        </dd>
      </div>
      <div>
        <dt>{label} · scores</dt>
        <dd>
          overall={a.scores.overallQuality.toFixed(2)} face=
          {a.scores.face !== undefined ? a.scores.face.toFixed(2) : 'n/a'} exposure=
          {a.scores.exposure.toFixed(2)} contrast={a.scores.contrast.toFixed(2)} sharpness=
          {a.scores.sharpness.toFixed(2)}
        </dd>
      </div>
      <div>
        <dt>{label} · latency / reasons</dt>
        <dd>
          {a.analysisTimeMs.toFixed(1)} ms · {a.reasonCodes.join(', ') || 'none'}
        </dd>
      </div>
    </>
  )
}
