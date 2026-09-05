# LivePhoto — Camera Capture Design (M2)

Status: M2 baseline. Describes the browser camera-acquisition architecture: `getUserMedia`
constraints, switching, frame scheduling, burst lifecycle, Blob lifecycle, stream cleanup,
mirroring, orientation, error mapping, privacy boundaries, browser limitations and fallbacks.

**M2 does not perform liveness detection.** See `PRODUCT_REQUIREMENTS.md` and `ROADMAP.md`.

---

## 1. Camera architecture

```
CameraIntroduction (explicit Start camera)
   -> useCaptureFlow (state machine) -> useCamera (session lifecycle)
   -> requestCameraStream (the ONLY getUserMedia call site)
   -> attach to a single stable <video> element (srcObject)
   -> captureBurst (rVFC or rAF scheduler) -> CaptureFrame[] blobs
   -> representative preview (middle frame) -> Preview / Retake / Use Photo
   -> CaptureBundle handed to the M3 seam via onBundleReady
```

- Camera APIs are infrastructure details; React components never call `getUserMedia` directly
  (M2 §4). All media access lives in `frontend/src/features/capture/media/`.
- The `<video>` element is a **single stable DOM node** kept mounted (visually hidden) from the
  permission phase through capture, so `srcObject` survives phase transitions.

## 2. Secure context & availability

Before requesting access, `checkCameraAvailability()` verifies:
`window.isSecureContext`, `navigator.mediaDevices`, `navigator.mediaDevices.getUserMedia`.
Failures map to deterministic codes `INSECURE_CONTEXT` / `CAMERA_API_UNAVAILABLE` (M2 §6).
Localhost is acceptable for development; production requires HTTPS.

## 3. getUserMedia constraints

Initial request is conservative and never uses restrictive `exact` values (M2 §8, §11):

```typescript
{
  audio: false, // microphone is never requested
  video: {
    facingMode: { ideal: 'user' },
    width: { ideal: 1280 },
    height: { ideal: 720 },
    frameRate: { ideal: 30, max: 30 },
  },
}
```

The browser may return different settings; the actual values are read from `track.getSettings()`
and reduced to a safe, non-identifying subset (`SafeTrackSettings`: width, height, frameRate,
aspectRatio, facingMode). `deviceId`/`groupId` are **never** logged, persisted, or exposed (M2 §19).

## 4. Front/rear camera & switching

- `facingMode` is the primary mobile concept (`user`/`environment`).
- **Preview mirroring** is presentation-only via `transform: scaleX(-1)` for the front camera;
  captured pixels keep the camera's natural orientation (M2 §13). Rear camera is never mirrored.
- `useCamera.switchCamera` requests the alternate camera **first** and only stops the current
  stream after the new one attaches, so a failed switch leaves the current camera usable (M2 §17).
  This is a deliberate refinement of M0/M2 §15's stop-first sketch, chosen to satisfy M2 §17;
  the overlap is brief and only occurs on platforms that permit concurrent streams.
- A stale async camera request (generation mismatch) is stopped and never adopted (M2 §53).
- A "Switch camera" button is only offered when `enumerateDevices()` reports >= 2 `videoinput`
  devices (best-effort; enumeration is an enhancement, not a security control) (M2 §16-17).

## 5. Frame scheduling

- Preferred: `HTMLVideoElement.requestVideoFrameCallback()` — works with actually presented frames
  and optionally exposes `mediaTime`/`presentedFrames` for duplicate-frame avoidance.
- Fallback: a `requestAnimationFrame` loop with `performance.now()` time spacing (M2 §25). No
  high-frequency polling loop.
- Feature detection (`"requestVideoFrameCallback" in video`) decides the path; compatibility never
  depends on the advanced API (M2 §24-25, §91-92).
- Captures are spaced at `burstDurationMs / burstFrameCount`; the first tick always captures.

## 6. Burst lifecycle & Blob lifecycle

```
MediaStream -> transient video frames -> 8 CaptureFrame Blobs -> representative preview
   +--> Retake: dispose all previous blobs, revoke preview URL, reacquire camera
   +--> Confirm: CaptureBundle exposed to the next pipeline stage (kept until disposed)
```

- Frames are encoded with `canvas.drawImage` (native `video.videoWidth/videoHeight`) +
  `canvas.toBlob` as `image/jpeg` (quality 0.95). **Base64 is never used for frame storage**
  (M2 §27-28).
- The canvas is reused across frames; no ImageData/Base64 copies are retained (M2 §83).
- `ImageCapture`, `WebCodecs`, `VideoFrame`, `MediaStreamTrackProcessor`, `OffscreenCanvas` are
  **not required paths** (M2 §29-30).
- Complete frames are retained — **never cropped to the face guide** — so later spoof validators
  can see phone borders, laptop edges, print boundaries and screen reflections (M2 §41, §81).
- Partial encoding failures are tolerated down to `minimumSuccessfulFrames` (6 of 8); below that
  the burst fails with `INSUFFICIENT_FRAMES` (M2 §35).

## 7. Preview / retake / confirm

- The representative preview uses the middle successful frame's Blob object URL directly; no
  lossy re-encode is created for display (M2 §34, §97).
- Every `URL.createObjectURL` is paired with `URL.revokeObjectURL` on retake, discard, unmount
  (M2 §47). The camera is stopped during preview (M2 §42).
- "Use photo" means **capture acquisition completed** — never LIVE/PASS/VERIFIED. The UI shows
  only "Photo captured successfully." (M2 §44-45).
- Retakes are not business-limited in M2 (M2 §98); the bundle is handed to M3 via
  `onBundleReady`.

## 8. Stream cleanup & privacy

- Every track is stopped via `stream.getTracks().forEach(t => t.stop())` on: preview transition,
  retake, switching, unmount, capture error, cancellation (M2 §48).
- When the document becomes hidden (`visibilitychange`), the camera is released and any unfinished
  burst is invalidated; an explicit resume/restart is required on return (M2 §49).
- React cleanup and media-track cleanup are primary; `pagehide` is also handled (M2 §50).
- Unexpected track `ended` is handled as a recoverable interruption (no frozen-frame illusion).

## 9. Error mapping

Browser `DOMException`s map to deterministic application codes (M2 §37-39):

| DOMException name | Application code |
|---|---|
| `NotAllowedError` | `CAMERA_PERMISSION_DENIED` |
| `NotFoundError` | `CAMERA_NOT_FOUND` |
| `NotReadableError` | `CAMERA_IN_USE_OR_UNREADABLE` |
| `OverconstrainedError` / `TypeError` | `CAMERA_CONSTRAINT_FAILED` |
| `AbortError` | `CAMERA_START_FAILED` |
| `SecurityError` | `INSECURE_CONTEXT` |
| `InvalidStateError` | `CAMERA_INTERRUPTED` |

Plus application-level codes: `CAMERA_API_UNAVAILABLE`, `CAMERA_START_FAILED`,
`CAMERA_SWITCH_FAILED`, `FRAME_CAPTURE_FAILED`, `INSUFFICIENT_FRAMES`, `VIDEO_NOT_READY`,
`UNKNOWN_CAMERA_ERROR`.

Customers see safe, actionable messages only; raw browser/device details are never shown and are
retained only as a `domName` for development diagnostics (M2 §38-39, §95).

## 10. Privacy boundaries

- M2 code must not intentionally persist image bytes in localStorage, sessionStorage, IndexedDB,
  Cache API, filesystem, downloads, cookies, URL query strings, logs or analytics (M2 §46).
  Browser/runtime internals may manage Blob backing storage; the application does not persist it.
- No gallery upload (`<input type="file">`), no `getDisplayMedia`, no download/save/copy actions
  (M2 §65-67).
- No fingerprinting: no fonts/canvas/WebGL/audio fingerprint collection (M2 §93).
- Error logs may contain the application error code, the DOMException *name*, the flow state and a
  request-free local operation ID — never frames, blobs, object URLs, device labels or IDs
  (M2 §95).

## 11. Security headers & CSP (production hosting)

- M2 uses a top-level redirect into LivePhoto (no embedding). Preserve `frame-ancestors 'none'`
  (already set by the backend security-headers middleware) unless a later bank integration
  explicitly requires iframing — changing to an iframe requires a deliberate
  Permissions-Policy/CSP redesign (M2 §61).
- Camera stays restricted to LivePhoto's own origin: `Permissions-Policy: camera=(self)`;
  microphone is not enabled; no wildcard camera origins (M2 §62).
- When the production frontend is hosted with a CSP, allow only the narrowly required local Blob
  preview, e.g. `img-src 'self' blob:` (and `media-src 'self' blob:` if needed). Do not relax
  `default-src *` (M2 §63).

## 12. Security assumption

> `getUserMedia()` proves that the browser supplied a media source; it does not prove that the
> source is a genuine physical camera or that the subject is live.

M2 makes no liveness/security conclusion from camera acquisition alone. Virtual-camera/injection
detection remains future scope (M2 §94; `THREAT_MODEL.md`).

## 13. Browser limitations

- `requestVideoFrameCallback` is not available on all historical browsers → rAF fallback.
- WebViews inherit the host app's camera permission policy; behavior varies by platform.
- `enumerateDevices` device counts are best-effort and permission-dependent.
- See `CAMERA_COMPATIBILITY_MATRIX.md` for the honest per-environment status (largely NOT TESTED
  until physical devices are exercised).

## 14. Local capture timing (M2 §82)

The capture flow records non-persisted, dev-only diagnostics: `camera_start_ms`,
`burst_duration_ms`, `total_capture_flow_ms`, frame count, total burst bytes, camera settings and
scheduler used. Shown only in the development diagnostics panel; nothing is sent anywhere yet.
This informs the eventual <5 s capture→decision budget (`VALIDATION_PIPELINE.md`).