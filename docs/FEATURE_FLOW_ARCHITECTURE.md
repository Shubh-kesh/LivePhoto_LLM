# LivePhoto — Feature Flow Architecture

Status: **LIVING DOCUMENT — feature-by-feature current architecture + evolution history.** It is
updated whenever a change affects a feature's flow (see the Architecture Documentation Rule in
`AGENTS.md`).

Conventions:

- Each section has **Current flow**, **Important decision rules**, **Retry/failure paths**,
  **Security/authority boundary**, an **Evolution history** table (`Date | Before | After | Why |
  Status`), and a **Next candidate improvement**.
- Anything under `Next candidate improvement` is **`NOT IMPLEMENTED`** and must not be read as
  current behaviour.
- Status values in history: `shipped`, `in-progress (uncommitted)`, `superseded`.

Date range: initial foundation `2026-09-05` → current `2026-09-11`.

---

## 1. Network / browser preflight

### Current flow

`frontend/src/features/connectivity/ConnectivityGate.tsx` wraps `/capture` and `/xbiz/live_photo`
(not `/dev/vlm-experiment`). It never requests camera permission and never mounts the journey until
preflight passes. `useConnectivity` (1) checks browser capabilities via feature detection, (2) uses
`navigator.onLine === false` as an offline hint only, (3) probes the backend `GET /api/v1/info`
(`cache: 'no-store'`, 4 s timeout, Zod-validated), (4) evaluates the version policy, and only then
becomes `ready`.

### Important decision rules

- Capability issues: `INSECURE_CONTEXT`, `CAMERA_API_UNAVAILABLE`, `CANVAS_API_UNAVAILABLE`,
  `BLOB_API_UNAVAILABLE`, `OBJECT_URL_UNAVAILABLE`, `REQUEST_ANIMATION_FRAME_UNAVAILABLE`.
- A fresh successful `/info` probe is the only way to reach `ready`; an `online` event or cached
  state never grants `ready`.
- Mid-session connectivity loss shows a blocking overlay and prevents new server operations until a
  real probe succeeds.

### Retry/failure paths

Unreachable/non-2xx/schema-invalid probe → `backend_unreachable`; offline hint → `offline`;
capability failure → `unsupported`; version/policy failure → `browser_update_required`
(non-dismissible). All are retryable by re-running the check.

### Security/authority boundary

Preflight is a **compatibility/UX gate only**. It must never influence liveness decisions, PASS
authorization, portrait authorization, fraud decisions, or callback security.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-10 | No preflight; failures surfaced later as capture errors | Capability probe + backend probe + policy evaluation before camera | Fail fast on unsupported/offline devices; cost + UX | shipped (`4400022`, `f812b83`) |
| 2026-09-10 | `online` event could clear an offline state | `online` always forces a fresh probe; single-flight | Stale/cached connectivity must not unlock the journey | shipped |

### Next candidate improvement

`NOT IMPLEMENTED`: latency/quality probing (measure real network for burst upload), and explicit
mid-flow token-expiry recovery UX.

---

## 2. Browser minimum-version policy

### Current flow

The backend publishes a server-controlled policy on `/api/v1/info` from
`backend/config/browser-support.json` (`browser-policy-v1`); the frontend evaluates the detected
browser against it in `browserPolicy.ts`.

### Important decision rules

- `policy === null` → `POLICY_UNAVAILABLE` (fail closed).
- `family === 'unknown'` → `UNSUPPORTED_BROWSER`.
- Missing/disabled entry → `UNSUPPORTED_BROWSER`.
- `majorVersion === null` → `VERSION_UNKNOWN` (never invent a version).
- `majorVersion < minimum_major` → `VERSION_TOO_OLD`; else `SUPPORTED`.
- Detection order: iOS first → Edge before Chrome → non-Chrome Chromium shells
  (`SamsungBrowser|OPR|Vivaldi`) fail closed as `unknown` → Android Chrome → Firefox → Chrome →
  Safari → unknown.

### Retry/failure paths

`UNSUPPORTED_BROWSER` / `VERSION_TOO_OLD` / `VERSION_UNKNOWN` / `POLICY_UNAVAILABLE` all block with
`browser_update_required` (no "continue anyway").

### Security/authority boundary

Browser/version detection is explicitly **not** an authentication or security boundary. The backend
controls the policy; the client only evaluates a compatibility decision.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-10 | No minimum-version policy | Server-published policy + fail-closed client evaluation | Prevent unsupported-browser capture failures in banking UAT | shipped |

### Next candidate improvement

`NOT IMPLEMENTED`: policy expiry/versioning telemetry and per-OS device matrix enforcement
(documented matrix only today).

---

## 3. Camera capture

### Current flow

`useCaptureFlow.startCamera` → `useCamera.start` → `getUserMedia` (audio off; `facingMode` ideal;
1280×720 ideal @ 30 fps, no `exact`). One Capture press starts a burst of 8 frames over ~1200 ms at
**native video resolution**; the best frame is kept. Camera switching stops the previous stream
first and recovers it on failure.

### Important decision rules

- Minimum 6 successful frames; fewer → `INSUFFICIENT_FRAMES` (frames cleared).
- Frame encoding uses `canvas.toBlob` (never Base64); per-frame timeout 1500 ms; overall deadline
  `intervalMs*frameCount + 2500` → `CAMERA_INTERRUPTED`.
- Stored frames are full-frame and **never mirrored** (mirroring is display-only) so spoof evidence
  is preserved.

### Retry/failure paths

Permission denied → error state with retry; track `ended`/`visibilitychange`/`pagehide` →
`INTERRUPTED` and stream stop; failed switch → attempt recovery of the previous camera.

### Security/authority boundary

Camera/capture is evidence acquisition. A technical failure is never converted into a quality or
liveness classification, and no capture state is persisted in the browser.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-05 | No capture foundation | Secure `getUserMedia` + burst capture | Core capability | shipped (`ff01292`) |
| 2026-09-07 | Basic capture | Mobile-tuned burst and lifecycle guards | Real-device reliability | shipped (`1a4fff2`, `de40b9f`, `d25ab55`) |

### Next candidate improvement

`NOT IMPLEMENTED`: front/rear multi-camera selection requested by the bank; capture under extremely
low light with adaptive exposure guidance.

---

## 4. Frontend image quality

### Current flow

`qualityEngine` analyses each frame (face detection/participation, exposure, contrast, sharpness,
eye state) and disposes it `ELIGIBLE` or `INELIGIBLE`. `bundleAnalyzer` aggregates; a bundle is
`QUALITY_READY` only with ≥ 3 eligible frames. `frameRanking` selects the representative frame
deterministically.

### Important decision rules

- Hard blockers: `NO_FACE`, `MULTIPLE_FACES`, `FACE_TOO_SMALL`, `FACE_TOO_LARGE`, `BLURRED`,
  `UNDEREXPOSED`, `OVEREXPOSED`, `LOW_CONTRAST`, `RESOLUTION_TOO_LOW`, `EYES_CLOSED`,
  `EYE_STATE_UNKNOWN`, `FACE_ANALYSIS_UNAVAILABLE`, `QUALITY_ANALYSIS_ERROR`. `FACE_OFF_CENTER` is
  the only tolerated reason.
- Thresholds (`quality-v1`): face coverage 0.08–0.6, min detection confidence 0.5, mean luminance
  0.25–0.85, dark ratio ≤ 0.4, bright ratio ≤ 0.35, min contrast 0.08, blur threshold 100.
- Eye state unknown ⇒ ineligible; an image is never assumed open/valid by default.
- A technical analysis failure is never converted into an image-quality classification.

### Retry/failure paths

`QUALITY_RETRY` → customer-facing retry copy (raw codes never shown); `ANALYSIS_UNAVAILABLE` → error
screen (not a silent pass); camera stream stays recoverable.

### Security/authority boundary

Quality is **preliminary UX/evidence**. Scores are not probabilities and never authorize LIVE/PASS.
The normalized face box is geometry guidance only.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-05 | No quality engine | Frame quality + face/eye acquisition engine | Reject unusable captures early | shipped (`73e2364`) |
| 2026-09-07 | Eye blink not evaluated | Eye state required (closed/unknown ⇒ retry) | Reject closed-eye captures | shipped (`d25ab55`) |
| 2026-09-11 | Face box used ad hoc | `faceBox.ts` normalized/clamped `x,y,w,h` passed to backend | Feed the backend integrity gate geometry | in-progress (uncommitted) |

### Next candidate improvement

`NOT IMPLEMENTED`: on-device passive PAD pre-signal; per-region exposure guidance.

---

## 5. Multiple / interfering-person handling

### Current flow

Two layers:

1. **Browser (UX):** `faceParticipation` marks a face participating only if it is confident,
   large enough, and near the primary face. `MULTIPLE_FACES` is raised only when ≥ 2 faces
   *participate*; small peripheral faces do not force rejection.
2. **Backend (authoritative):** the VLM reports `subject_count` and `secondary_person_state`; the
   coherence matrix decides. `subject_count` is diagnostic evidence; `secondary_person_state` is the
   authoritative multi-person gate.

### Important decision rules

- `LIVE + MULTIPLE + BACKGROUND` → **PASS** (portrait eligible) — a background person is allowed.
- `LIVE + MULTIPLE + INTERFERING` / `MULTIPLE + UNCERTAIN` / `ZERO + NONE` / `UNCERTAIN + UNCERTAIN`
  → RETRY.
- A contradictory pair (e.g. `ONE + BACKGROUND`) fails closed → RETRY.

### Retry/failure paths

Interfering/secondary person → retry with `MULTIPLE_FACES` reason; contradictory/invalid state →
fail-closed retry.

### Security/authority boundary

The browser face count is UX only. The **server** is authoritative and the decision is
capture-bound. Do not modify the person-state matrix without an explicit milestone.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-10 | Single-person VLM gate only | `subject_count` + `secondary_person_state` normalized fields; coherence matrix | Distinguish interfering vs background person | shipped (`192bbbb`) |
| 2026-09-10 | `MULTIPLE` could block portrait | `MULTIPLE + BACKGROUND` portrait-eligible; interfering/uncertain retry | Portrait-safe person-state policy | shipped (`c100c8d`) |

### Next candidate improvement

`NOT IMPLEMENTED`: explicit background-removal verification for `MULTIPLE + BACKGROUND` (the
portrait matte must reliably exclude the distant person) — currently relies on segmentation quality.

---

## 6. Backend VLM / liveness

### Current flow

`POST .../liveness` derives capture identity server-side, checks the evaluation cache under a short
lock, sets a single-flight claim, calls the configured provider (`VLM_PROVIDER` only), then
re-locks, does a stale check, persists the normalized result, and writes either the experimental
result or the canonical decision.

### Important decision rules

- Schema `vlm-result-v3`, prompt `vlm-passive-v3`, decision version `liveness-v3`.
- Strict parsing: missing/invalid `subject_count` or `secondary_person_state` is a schema failure —
  never defaulted.
- `SCREEN_REPLAY` / `PRINT_ATTACK` → FAIL regardless of person state.
- Provider/network/schema error → fail-closed RETRY, portrait forbidden.
- Legacy/old-schema cached evaluations are never reused for PASS.

### Retry/failure paths

`LIVENESS_IN_PROGRESS` (202) for a fresh concurrent claim; `LIVENESS_UNAVAILABLE` (502) on provider
failure; `STALE_EVALUATION` (409) when the capture changed during evaluation (result persisted
`stale=True, promoted=False`).

### Security/authority boundary

The provider is chosen by server config only; the browser cannot influence the identity or the
decision. Model output is **evidence**, not authorization — the mapping + capture binding decide.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-06 | VLM baseline with raw outputs | Normalized schema + strict parsing | Consistent evidence contract | shipped (`18cae5d`, `13bc789`) |
| 2026-09-10 | Single classification | Added subject/person-state + coherence + fail-closed | Reduce false PASS with multiple people | shipped (`192bbbb`, `c100c8d`) |

### Next candidate improvement

`NOT IMPLEMENTED`: M6 accuracy-driven spoof detection and calibrated confidence. VLM output must not
be treated as calibrated probability.

---

## 7. Canonical decision binding

### Current flow

The browser liveness route writes `decisions/decision.json` with `source="vlm"`, `version="liveness-v3"`,
and metadata binding `attempt_id`, `selected_sha256`, `liveness_identity`, provider/model,
classification, person-state, prompt, and schema. A new capture invalidates prior
decision/portrait/VLM/authorization artifacts.

### Important decision rules

`has_current_canonical_pass` requires: decision exists; outcome `PASS`; source `vlm`; metadata
matches the **current** capture; schema is current; and the metadata itself satisfies the
portrait-eligible person-state rule. Submit additionally requires a current portrait authorization.

### Retry/failure paths

Missing/stale/mismatched decision → `NOT_READY` (412); re-evaluation on new capture.

### Security/authority boundary

The canonical decision is the **only** authorization boundary for portrait/submit. The experimental
`vlm/result.json` is never consulted for submission.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-08 | Experimental result used for flow | Persisted canonical decision; capture-bound | Server-authoritative, replay-safe | shipped (`ff05477`) |
| 2026-09-10 | Person-state not part of binding | Portrait-eligible person-state required inside the canonical metadata | Prevent a stale/contradictory PASS | shipped (`c100c8d`) |

### Next candidate improvement

`NOT IMPLEMENTED`: decision TTL / explicit re-verification policy for long-lived sessions.

---

## 8. Portrait processing

### Current flow

On an authoritative PASS (and under capture authorization + single-flight), the pipeline runs:
selected original → MODNet matting → **raw matte integrity gate** → protected refinement →
**post-refinement integrity gate** → passport crop → white-background composite → identity-specific
candidate → promotion after re-validating the current capture/PASS.

### Important decision rules

- `portrait-matte-integrity-v1`: face retention ≥ 0.55, head retention ≥ 0.45, left/right balance ≥
  0.35, primary-component face overlap ≥ 0.55 (foreground threshold 0.5).
- Refinement must not drop face retention > 0.15 or balance > 0.25 versus raw; otherwise revert to
  the raw matte.
- The face box is **required** for customer portrait generation; missing/invalid → fail closed.
- Original pixels only: alpha + crop + background composite. No generative editing.

### Retry/failure paths

Structurally invalid raw matte → `PORTRAIT_QUALITY_FAILED` (HTTP 422, retryable) → customer retry;
**no portrait promoted**. Technical failures → `TECHNICAL_ERROR`; decode mismatch →
`PORTRAIT_INVALID_SOURCE`.

### Security/authority boundary

Portrait authorization is bound to the current canonical PASS and capture identity; promotion is
re-validated under lock and stale candidates are discarded. The integrity gate is a **quality**
gate, never liveness/identity authority.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-07 | No portrait pipeline | MODNet matting + crop + composite + storage | Produce reviewable portrait | shipped (`60cd4e0`) |
| 2026-09-07 | v1 crop framing | `passport-crop-v3` (hair/shoulder balance) | Natural passport framing | shipped (`3b77506`, `d53e882`) |
| 2026-09-07 | Plain matte compositing | `matte-refinement-v3` region-aware refinement | Dark clothing / tear artifacts | shipped (`d25ab55`) |
| 2026-09-11 | Technical success = portrait | `portrait-matte-integrity-v1` raw+refined gate, fail closed | Confirmed corrupted portrait promoted | in-progress (uncommitted) |

### Next candidate improvement

`NOT IMPLEMENTED`: an offline-benchmarked **fallback segmentation model** (see
`docs/PORTRAIT_SEGMENTATION_EVALUATION.md`). Candidate: BiRefNet. It is **not** integrated; a future
architecture would retry segmentation on the same original before asking the user to retake. It must
reuse the same integrity gate and identity rules.

---

## 9. Transaction / artifact lifecycle

### Current flow

Created via `create_transaction_with_generated_id` (exclusive `mkdir`, bounded collision retry).
Statuses progress `CREATED → CAPTURE_READY / LAUNCHED → VLM_EVALUATED / DECISION_READY →
PORTRAIT_READY → COMPLETED`; terminal `ATTEMPT_LIMIT_EXCEEDED` / `FAILED` / `TECHNICAL_ERROR`.

### Important decision rules

- Internal IDs `LP-<UTC>-<rand>`; legacy 32-hex IDs remain readable.
- Artifacts are transaction-relative; absolute paths never exposed.
- Metadata writes are atomic (temp → fsync → rename); per-transaction lock serializes mutations.
- External consumer IDs are never filesystem paths.

### Retry/failure paths

Collision → retry fresh suffix; missing artifact → typed not-found; invalid id/path → rejected.

### Security/authority boundary

Root confinement + symlink rejection at the store layer; allowlisted artifact reads only.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-07 | No transaction storage | Filesystem per-transaction layout + atomic writes + lock | Durable artifacts | shipped (`60cd4e0`) |
| 2026-09-11 | Opaque/legacy IDs | Human-readable UTC `LP-…` IDs, legacy still accepted | Operability/traceability without breaking reads | in-progress (uncommitted) |

### Next candidate improvement

`NOT IMPLEMENTED`: retention/purge jobs; complete canonical artifact map for non-canonical files.

---

## 10. Attempt / fraud policy

### Current flow

One attempt = one Capture press. The browser registers an attempt (opaque `attempt_id`, SHA-256
hashed) via `/browser/attempts` or implicitly with `/browser/capture`. Counts/limits are
server-authoritative.

### Important decision rules

- Browser may report only allowlisted reasons and results `QUALITY_RETRY | QUALITY_ELIGIBLE`.
- Forbidden authoritative values (`PASS`, `LIVE`, `APPROVED`, `VERIFIED`, `SCREEN_REPLAY`,
  `PRINT_ATTACK`) are rejected.
- One upload per attempt (replay → `UPLOAD_ALREADY_RECORDED`).
- Limit: warning 5, warning-again 7, hard limit 10 (per-consumer override). Reaching the limit makes
  the transaction terminal `ATTEMPT_LIMIT_EXCEEDED`.

### Retry/failure paths

Disallowed reason/result → 400; replay → 409; terminal transaction blocks further capture.

### Security/authority boundary

Attempt counts and terminal decisions are server-side. The client cannot claim PASS or reset counts.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-08 | No attempt accounting | Server-authoritative attempts + limits + replay protection | Fraud/abuse control | shipped (`ff05477`, `4824dab`) |

### Next candidate improvement

`NOT IMPLEMENTED`: cross-session device/velocity fraud signals; attempt-limit escalation to review.

---

## 11. Callback / redirect

### Current flow

`POST /browser/submit` verifies canonical PASS + current portrait + JPEG integrity, resolves the
consumer profile, and sends a signed callback with a stable idempotency key, then returns a
validated redirect.

### Important decision rules

- Acknowledged callbacks return the stored redirect without re-calling.
- Retry only transient failures (network / 429 / 5xx) with backoff; other 4xx and non-JSON are
  terminal.
- Redirect must be exact-origin, HTTPS outside local, no userinfo/fragments; query is allowed;
  redirects are never followed.

### Retry/failure paths

Transient → `FAILED` (retryable) + `CALLBACK_FAILED` (502); terminal → `FAILED` (non-retryable);
invalid redirect → `INVALID_REDIRECT` (502).

### Security/authority boundary

Only the backend validates the redirect origin and sends the callback; callback credentials are
never logged and the Base64 image payload is never persisted.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-08 | No callback | Signed callback + redirect validation + idempotency | Close the bank integration loop | shipped (`ff05477`, `4824dab`) |

### Next candidate improvement

`NOT IMPLEMENTED`: async/out-of-band callback retry (today it runs inline under the transaction
lock).

---

## 12. Manual review

### Current flow

**Not implemented.** `DecisionOutcome.REVIEW` and `SessionState.REVIEW` are documented domain
placeholders only. There is no review endpoint, store, RBAC, or `TransactionStatus.REVIEW`, and
`status.py` has no REVIEW mapping. The frontend "review" is the **customer** reviewing the processed
portrait, not manual review.

### Important decision rules

None currently active.

### Retry/failure paths

N/A (not implemented).

### Security/authority boundary

Planned to be internal, restricted, and audited (M13). Do not claim it exists.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-05 | REVIEW enum placeholder | Unchanged | Reserved for a future milestone | not implemented |

### Next candidate improvement

`NOT IMPLEMENTED`: manual review workflow (case queue, reviewer roles, audit, SLA) — M13.

---

## 13. Standalone `/capture`

### Current flow

Experiment-gated diagnostics: create transaction → upload original → liveness (normalized VLM
result, no canonical decision) → optional portrait if `portrait_allowed` → artifact read. The SPA
shows a review screen and optional VLM diagnostics.

### Important decision rules

- `_guard_experiment` hard-blocks production and UAT unless explicitly enabled.
- Uses the same VLM mapping and portrait-eligibility rule, but persists `vlm/result.json` and
  `VLM_EVALUATED` (not a canonical decision).
- No callback, no redirect, no submission.

### Retry/failure paths

Typed errors (`LIVENESS_UNAVAILABLE`, `PORTRAIT_QUALITY_FAILED`, etc.); the UI maps them to safe
messages.

### Security/authority boundary

Diagnostics only; never a production authorization path. Production must use the integrated flow.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-07 | Integrated-only flow | Standalone `/capture` diagnostics with experiments router | Developer/QA diagnostics | shipped (`65685c9`, `ac01c7f`, `cc6ad07`) |

### Next candidate improvement

`NOT IMPLEMENTED`: keep or retire the standalone path once M6 diagnostics replace it.

---

## 14. Integrated `/xbiz/live_photo`

### Current flow

Launch session → redeem opaque token → browser session (HttpOnly `lp_session` + readable `lp_csrf`)
→ capture → liveness (canonical) → portrait → review → submit → callback → redirect. External IDs
are preserved verbatim and never used as paths. `GET /browser/session` reports `submission_ready`
only with a current canonical PASS and current portrait authorization.

### Important decision rules

- S2S auth: JWT/JWKS or local-dev constant-time; requested `source` must match the identity.
- Consumer request options are allowlisted; UAT/production require bearer callback auth.
- Newest ACTIVE session redemption invalidates the previous active session.
- Terminal transaction statuses block restart.

### Retry/failure paths

Unknown/expired token → launch-outcome redirect; duplicate external ID → `TRANSACTION_EXISTS` (409);
`UPLOAD_ALREADY_RECORDED` (409); `NOT_READY` (412); callback failures as in §11.

### Security/authority boundary

Opaque 256-bit tokens persisted only as SHA-256 hashes; browser/session/CSRF enforcement at the edge;
all authorization is server-side and capture-bound.

### Evolution history

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-08 | No bank integration | Launch sessions + opaque token + browser session + callback | End-to-end bank journey | shipped (`ff05477`, `4824dab`) |
| 2026-09-10 | Person-state not enforced before PASS | Portrait-safe person-state enforced end-to-end | Correct bank-facing outcome | shipped (`c100c8d`) |
| 2026-09-11 | Corrupted portrait could be promoted | Portrait integrity gate fails closed | Confirmed real failure | in-progress (uncommitted) |

### Next candidate improvement

`NOT IMPLEMENTED`: multi-tenant consumer onboarding automation; richer consumer status webhooks.

---

## Appendix — Cross-cutting evolution

| Date | Before | After | Why | Status |
|---|---|---|---|---|
| 2026-09-05 | Empty repo | Engineering foundation | Baseline | shipped |
| 2026-09-06 | Ad-hoc UI | Banking-grade guided capture UX | Product readiness | shipped (`636bc32`) |
| 2026-09-08 | OpenCode guidance absent | `AGENTS.md` rules added | Agent-safe changes | shipped (`07cfa44`) |
| 2026-09-11 | Architecture docs scattered | Two living architecture documents + AGENTS rule | Keep architecture current | in-progress (uncommitted) |
