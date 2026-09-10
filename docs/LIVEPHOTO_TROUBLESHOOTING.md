# LivePhoto — Troubleshooting

Concise history of bugs, configuration issues, troubleshooting steps, root causes, and fixes
discovered during LivePhoto development and local/UAT testing. Keep each entry short and practical.

For every future issue, append or update this document.

## Quick Checks Before Debugging

1. Confirm backend CWD:

   ```
   lsof -a -p "$(lsof -tiTCP:8000 -sTCP:LISTEN | head -1)" -d cwd
   ```

   Expected:
   `.../LivePhoto/backend`

2. Confirm backend runtime settings with `Settings()`.

3. Confirm frontend local M5.8 API base:

   ```
   VITE_API_BASE_URL=
   ```

4. Restart backend/frontend after `.env` changes.

5. Confirm ports:
   - Backend: 8000
   - Frontend: 5173
   - Stub consumer: 3001

6. For VLM:

   ```
   VLM_EXPERIMENT_ENABLED=true
   ```

   in local environment.

7. For local M5.8 manual canonical PASS testing:
   ```
   DECISION_TEST_WRITER_ENABLED=true
   ```
   Never enable this in UAT/production.

---

## 1. Backend started from wrong working directory

**Milestone:** M5.8  
**Type:** Runtime / Configuration  
**Symptom:**  
S2S launch API returned:

```
INTEGRATION_NOT_CONFIGURED
S2S integration is not configured
```

even though `APP_ENV=local`, `S2S_AUTH_MODE=local_dev`, `S2S_LOCAL_DEV_TOKEN=<configured>` were correctly
present in `backend/.env`.

**Troubleshooting:**  
A standalone `Settings()` check from `backend/` showed the correct configuration. Then checked the
actual Uvicorn process:

```
PID=$(lsof -tiTCP:8000 -sTCP:LISTEN | head -1)
lsof -a -p "$PID" -d cwd
```

Actual CWD was `/Users/Shubhansh/Developer/LivePhoto` instead of
`/Users/Shubhansh/Developer/LivePhoto/backend`.

**Root cause:**  
Pydantic Settings uses `env_file=".env"`, so starting Uvicorn from the project root caused the
backend process not to load `backend/.env`. It also caused relative paths such as
`CONSUMER_PROFILES_PATH=config/consumers.local.json` to resolve from the wrong directory.

**Fix:**  
Always start the backend from the backend directory:

```
cd /Users/Shubhansh/Developer/LivePhoto/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Verification:**

```
lsof -a -p "$(lsof -tiTCP:8000 -sTCP:LISTEN | head -1)" -d cwd
```

Expected CWD: `/Users/Shubhansh/Developer/LivePhoto/backend`

**Status:** Fixed

---

## 2. Consumer reported as unknown or inactive

**Milestone:** M5.8  
**Type:** Configuration  
**Symptom:**

```
FORBIDDEN
Unknown or inactive consumer
```

when calling `POST /api/v1/integration/launch-sessions`.

**Root cause:**  
In `local_dev` authentication mode the request body's `source` must exactly match an active consumer
profile. For example `"source": "D365"` requires `"consumer_id": "D365", "active": true` in
`backend/config/consumers.local.json`.

**Fix:**  
Use the configured `consumer_id` exactly and ensure `active=true`.

**Verification:**  
Launch API successfully returned `launch_session_id`, `launch_url`, `expires_at`, `transaction_id`.

**Status:** Fixed

---

## 3. Browser API requests caused CORS errors

**Milestone:** M5.8  
**Type:** Configuration  
**Symptom:**  
Frontend running on `http://localhost:5173` was directly calling
`http://localhost:8000/api/v1/browser/session` and the browser reported CORS errors.

**Root cause:**  
`frontend/.env` contained `VITE_API_BASE_URL=http://localhost:8000`. This bypassed the M5.8
same-origin Vite proxy. `vite.config.ts` was already correctly configured:
`'/api' -> http://localhost:8000` and `'/xbiz/live_photo/l' -> http://localhost:8000`.

**Fix:**  
For local M5.8 testing set `VITE_API_BASE_URL=` (keep it blank). Restart Vite after changing `.env`.

**Verification:**  
Browser Network request became `http://localhost:5173/api/v1/browser/session` and Vite proxied it
internally to FastAPI.

**Status:** Fixed

---

## 4. Local canonical PASS writer returned 404

**Milestone:** M5.8  
**Type:** Configuration / Testing  
**Symptom:**

```
POST /api/v1/dev/test-decision
404 Not Found
```

after successful capture.

**Root cause:**  
The local-only canonical decision test endpoint is registered only when `APP_ENV` is
`local`/`test`/`development` **AND** `DECISION_TEST_WRITER_ENABLED=true`. The local `.env` had
`DECISION_TEST_WRITER_ENABLED=false`.

**Fix:**  
For local manual M5.8 testing only: `DECISION_TEST_WRITER_ENABLED=true`, then restart the backend.

Important: this must **never** be enabled in UAT or production.

**Verification:**  
`POST /api/v1/dev/test-decision -> 200` and portrait preparation proceeded.

**Status:** Fixed

---

## 5. Processed portrait GET returned CSRF_INVALID

**Milestone:** M5.8  
**Type:** Code Bug  
**Symptom:**

```
POST /api/v1/browser/portrait -> 200
GET  /api/v1/browser/portrait -> 403
```

Response: `CSRF_INVALID / CSRF validation failed`. The processed portrait appeared broken in the UI.

**Root cause:**  
`GET /browser/portrait` contained `require_csrf(request, record)`. The portrait is rendered through
an HTML `<img>` request, and an `<img>` request cannot add the custom `X-CSRF-Token` header. CSRF
protection is for state-changing requests, while this endpoint is read-only.

**Fix:**  
Keep `require_active_session(request)` but remove `require_csrf(request, record)` from
`GET /browser/portrait`. The endpoint remains protected by the authenticated browser session without
incorrectly requiring CSRF for an image GET. (Confirmed present in current
`backend/app/api/v1/browser.py`.)

**Verification:**  
`GET /api/v1/browser/portrait -> 200` and the processed portrait displayed successfully.

**Status:** Fixed

---

## 6. Submit returned CALLBACK_FAILED

**Milestone:** M5.8  
**Type:** Testing / Runtime  
**Symptom:**

```
POST /api/v1/browser/submit -> 502
CALLBACK_FAILED
Callback failed; please retry
```

**Troubleshooting:**  
Checked callback profile: `"url": "http://localhost:3001/livephoto/callback"`,
`"auth_type": "none"`. Checked whether the local consumer stub was listening:

```
lsof -nP -iTCP:3001 -sTCP:LISTEN
```

Started the stub consumer when required:

```
cd frontend
node e2e/stub-consumer.mjs
```

**Root cause:**  
The stub consumer was not running (or the callback URL did not match port 3001), so the callback
could not be delivered.

**Fix:**  
Keep the stub consumer running during local callback testing and ensure the consumer profile
callback URL matches port 3001.

**Verification:**  
After Submit, the browser successfully redirected to `http://localhost:3001/complete` and the
stub-consumer received the callback.

**Status:** Fixed

---

## 7. VLM experiment showed unavailable / providers returned 403

**Milestone:** M5.8 / M5.6 integration  
**Type:** Runtime / Configuration  
**Symptom:**

```
GET /api/v1/experiments/vlm/providers
403 Forbidden
```

UI displayed "VLM experiment unavailable". Occurred through both localhost and Cloudflare.

**Latest code verification:**  
The VLM providers endpoint calls a guard that checks `settings.vlm_experiment_available`. For
`APP_ENV=local` this requires `VLM_EXPERIMENT_ENABLED=true`. `403` corresponds to `VLM_DISABLED`.

**Root cause:**  
The backend had again been started with working directory
`/Users/Shubhansh/Developer/LivePhoto` instead of
`/Users/Shubhansh/Developer/LivePhoto/backend`, so `backend/.env` was not loaded and
`VLM_EXPERIMENT_ENABLED` fell back to its default `false`.

**Fix:**  
Always start the backend from the backend directory:

```
cd /Users/Shubhansh/Developer/LivePhoto/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify local `.env` contains `APP_ENV=local` and `VLM_EXPERIMENT_ENABLED=true`.

**Verification:**

```
uv run python - <<'PY'
from app.core.config import Settings
s = Settings()
print("app_env =", repr(s.app_env))
print("vlm_experiment_enabled =", repr(s.vlm_experiment_enabled))
print("vlm_experiment_available =", repr(s.vlm_experiment_available))
PY
```

Expected: `app_env = 'local'`, `vlm_experiment_enabled = True`,
`vlm_experiment_available = True`. Then `GET /api/v1/experiments/vlm/providers -> 200`.

**Status:** Fixed

---

## 8. Consumer profile relative path correction

**Milestone:** M5.8  
**Type:** Configuration  
**Issue:**  
Backend is normally started from `backend/`, therefore `CONSUMER_PROFILES_PATH` must be relative to
`backend/`.

Correct local value:

```
CONSUMER_PROFILES_PATH=config/consumers.local.json
```

This resolves to `LivePhoto/backend/config/consumers.local.json`. Do **not** use
`backend/config/consumers.local.json` when Uvicorn already starts from `backend/`, because that would
resolve to `LivePhoto/backend/backend/config/...`.

**Verification:**

```
uv run python - <<'PY'
from pathlib import Path
from app.core.config import Settings

s = Settings()
p = Path(s.consumer_profiles_path)

print(p.resolve())
print(p.exists())
PY
```

Expected: a path under `backend/config` and `exists=True`.

**Status:** Fixed

---

## 9. VLM experiment temporarily displayed and then changed to unavailable

**Milestone:** M5.8 / pre-M6  
**Type:** Configuration  
**Symptom:**  
The VLM experiment panel appeared briefly and then changed to:

```
VLM experiment is unavailable in this environment.
```

**Observed:**

- Backend `GET /api/v1/experiments/vlm/providers` = 200
- Vite proxy `GET /api/v1/experiments/vlm/providers` = 200
- Latest Git matched

**Root cause:**  
`frontend/.env` had previously contained a Cloudflare backend URL for `VITE_API_BASE_URL`. This made
the browser reach the experiment API through the tunnel instead of the M5.8 same-origin Vite proxy,
so the panel ended up in its controlled "unavailable" state.

Correct M5.8 same-origin local setting is:

```
VITE_API_BASE_URL=
```

(blank). After using the blank same-origin base, Vite proxy routing worked correctly and the VLM
experiment became available.

**Troubleshooting reminder:**  
Always verify the actual backend process CWD is `.../LivePhoto/backend` before debugging unexpected
backend configuration behavior:

```
lsof -a -p "$(lsof -tiTCP:8000 -sTCP:LISTEN | head -1)" -d cwd
```

**Fix:**  
Set `VITE_API_BASE_URL=` (blank) in `frontend/.env` and restart Vite.

**Verification:**  
`GET /api/v1/experiments/vlm/providers` through the Vite proxy returned 200 and the VLM experiment
panel became available.

**Status:** Fixed

---

## 10. Standalone /capture review mode flag

**Milestone:** pre-M6  
**Type:** Configuration  
**What it controls:**  
`VITE_VLM_EXPERIMENT_UI_ENABLED` selects the standalone `/capture` review experience only. It does
NOT affect `/xbiz/live_photo` and does NOT turn backend liveness validation on/off.

- `true` (diagnostic/manual): current flow — raw-capture Review (`Retake` / `Use photo`) plus the
  VLM experiment test panel. The diagnostic panel may show results from any selected provider
  (Gemini/OpenRouter/mock), but those results never authorize the normal final portrait.
- `false` (streamlined): quality-eligible captures bypass the raw review; the backend evaluates the
  stored capture with the configured authoritative provider (`VLM_PROVIDER`); only backend-confirmed
  `LIVE` allows portrait generation. The customer sees a processed-portrait review
  (`Retry` / `Use photo`) that completes with the normal standalone success screen. No callback.

**How to test each mode:**  
- Diagnostic/manual flow:
  ```
  VITE_VLM_EXPERIMENT_UI_ENABLED=true
  ```
- Streamlined flow:
  ```
  VITE_VLM_EXPERIMENT_UI_ENABLED=false
  ```
- Docker/public runtime equivalent:
  ```
  LIVEPHOTO_VLM_EXPERIMENT_UI_ENABLED=true|false
  ```

**Notes:**  
- The streamlined standalone flow uses the experiment transaction API
  (`POST /api/v1/transactions`, `POST /api/v1/transactions/{id}/liveness`,
  `POST /api/v1/transactions/{id}/portrait`), which is gated on `VLM_EXPERIMENT_ENABLED=true` and
  hard-blocked in uat/production. Portrait generation is LIVE-gated server-side.
- If portrait preparation shows a safe error, verify `VLM_EXPERIMENT_ENABLED=true`,
  `VLM_PROVIDER` is set (e.g. `groq` or `mock`), and the backend CWD (see Quick Checks).

**Status:** Fixed

---

## 11. Groq liveness gate replaces the forced test-PASS scaffold

**Milestone:** pre-M6  
**Type:** Code Bug / Architecture correction  
**Symptom:**  
The previous pre-M6 `/xbiz/live_photo` automatic flow used:

```
upload -> writeTestDecision() -> portrait
```

`writeTestDecision()` only wrote a forced local `PASS`; it performed NO real Groq/VLM liveness
gating, so a spoofed image could reach portrait processing when the test writer was enabled.

**Root cause:**  
The canonical decision was being manufactured by a local test endpoint instead of a
server-authoritative provider evaluation.

**Corrected flow (both `/xbiz/live_photo` and streamlined `/capture`):**

```
upload -> backend reads stored selected-original
       -> backend invokes configured VLM_PROVIDER (e.g. groq)
       -> backend normalizes + persists the result
       -> LIVE only -> canonical DecisionOutcome.PASS -> portrait allowed
```

- `/xbiz/live_photo` uses `POST /api/v1/browser/liveness` (session + CSRF; provider from backend
  config only). A new physical capture/new attempt causes a fresh evaluation; the same attempt+image
  is idempotent (single provider call).
- Streamlined `/capture` uses `POST /api/v1/transactions/{id}/liveness` (experiment-gated) and the
  existing LIVE-gated `POST /api/v1/transactions/{id}/portrait`.
- The customer path no longer depends on `DECISION_TEST_WRITER_ENABLED=true`. The dev
  `/api/v1/dev/test-decision` endpoint remains available only in local/test/development with the
  flag enabled.
- Non-LIVE (`SCREEN_REPLAY`/`PRINT_ATTACK`/`QUALITY_FAILURE`/`UNCERTAIN`) and provider errors always
  fail closed: no portrait, no Submit. `5/7/10` attempt policy is unchanged.

**Verification:**  
- `DECISION_TEST_WRITER_ENABLED=false` with `VLM_PROVIDER=mock`/`groq` returning `LIVE` still
  completes the `/xbiz/live_photo` happy path (test
  `test_customer_xbiz_path_works_without_test_writer`).
- `SCREEN_REPLAY`/`PRINT_ATTACK`/`QUALITY_FAILURE`/`UNCERTAIN` and provider errors block portrait.

**Status:** Fixed

---

## 12. New capture must invalidate/supersede previous liveness authorization

**Milestone:** pre-M6  
**Type:** Code Bug / Security hardening  
**Hazard:**  
A stale `PASS` or stale processed portrait from an earlier capture must never authorize a newer
capture. Without server-side binding, these attack/failure flows were possible:

- attempt 1 → LIVE → PASS → portrait A
- attempt 2 uploads a new image (spoof)
- stale PASS from attempt 1 could still authorize portrait, and stale portrait A could be
  submitted, before attempt 2's liveness runs.

**Server-side binding rule (now implemented):**
1. `POST /browser/capture` persists `capture/capture.json` (attempt_id + selected-original SHA-256 +
   config versions) and, atomically under the per-transaction lock, removes the previous
   decision/portrait/VLM artifacts and returns the transaction to `CAPTURE_READY`.
2. Liveness evaluation identity is derived SERVER-SIDE from the stored capture
   (attempt_id + SHA-256); the browser cannot change it.
3. The canonical decision is bound to the capture via metadata
   (`attempt_id`, `selected_sha256`, `liveness_identity`, provider/model/classification/versions)
   and `liveness/<identity>.json` evidence. `has_current_canonical_pass()` verifies the decision is
   PASS, source `vlm`, and matches the CURRENT stored capture.
4. Portrait processing writes `portrait/authorization.json` (decision_id + attempt_id +
   selected_sha256 + liveness_identity + portrait SHA-256). GET/POST `/browser/portrait` and
   `/browser/submit` require this authorization to match the current capture/PASS/portrait.
5. Stale in-flight provider results are never promoted: before writing a canonical decision the
   transaction lock is reacquired, the current capture identity is recomputed, and a mismatch
   yields a safe `STALE_EVALUATION`/conflict instead of a PASS.
6. Provider calls are single-flight per identity (claim file) and provider failures are cached per
   identity (fail closed), so React StrictMode/re-renders/concurrent requests cannot multiply Groq
   calls for the same capture.

**Status:** Fixed

---

## 13. Mobile portrait PORTRAIT_INVALID_SOURCE caused by passport crop larger than source width

**Milestone:** pre-M6  
**Type:** Code Bug (not Cloudflare)  
**Symptom:**  
On a mobile/portrait source such as `720x1280`, portrait processing failed with:

```
PORTRAIT_INVALID_SOURCE
We couldn't prepare your photo.
```

with an internal broadcasting `ValueError` in `composite_solid`.

**Root cause:**  
`passport_crop()` could return a CropBox whose width exceeded the source width (e.g. desired 3:4
width `1143` for a `720`-wide source, producing `CropBox(x0=-137, ...)`). The subsequent
`alpha[-137:720, ...]` used negative NumPy slicing, so the alpha and foreground RGB crop shapes
mismatched and `composite_solid` failed. This was **not** a Cloudflare/CORS/environment issue.

**Fix (backend/app/portrait/crop.py):**  
The desired 3:4 frame is now scaled down to the largest 3:4 frame that fits inside the source in
**both** dimensions before positioning/clamping, so CropBox coordinates are always inside the
source:

```
0 <= x0 < x1 <= image_width
0 <= y0 < y1 <= image_height
crop_width <= image_width
crop_height <= image_height
```

Face centering and hair/shoulder margins are preserved where physically possible. A defensive
foreground-vs-alpha spatial-dimension assertion in `PortraitProcessor` raises a typed
`PORTRAIT_INVALID_SOURCE` (with structured logging) if they ever mismatch.

**Verification:**  
- New crop invariants/property tests (720x1280 wide shoulders, narrow portrait, taller-than-source,
  multiple source sizes).
- New processor tests: mobile `720x1280` no-broadcasting success; deliberate alpha/image dimension
  mismatch rejected with `PORTRAIT_INVALID_SOURCE`.
- Full backend regression green.

**Status:** Fixed

**Milestone:** pre-M6  
**Type:** Code Bug / Security hardening  
**Hazard:**  
A stale `PASS` or stale processed portrait from an earlier capture must never authorize a newer
capture. Without server-side binding, these attack/failure flows were possible:

- attempt 1 → LIVE → PASS → portrait A
- attempt 2 uploads a new image (spoof)
- stale PASS from attempt 1 could still authorize portrait, and stale portrait A could be
  submitted, before attempt 2's liveness runs.

**Server-side binding rule (now implemented):**
1. `POST /browser/capture` persists `capture/capture.json` (attempt_id + selected-original SHA-256 +
   config versions) and, atomically under the per-transaction lock, removes the previous
   decision/portrait/VLM artifacts and returns the transaction to `CAPTURE_READY`.
2. Liveness evaluation identity is derived SERVER-SIDE from the stored capture
   (attempt_id + SHA-256); the browser cannot change it.
3. The canonical decision is bound to the capture via metadata
   (`attempt_id`, `selected_sha256`, `liveness_identity`, provider/model/classification/versions)
   and `liveness/<identity>.json` evidence. `has_current_canonical_pass()` verifies the decision is
   PASS, source `vlm`, and matches the CURRENT stored capture.
4. Portrait processing writes `portrait/authorization.json` (decision_id + attempt_id +
   selected_sha256 + liveness_identity + portrait SHA-256). GET/POST `/browser/portrait` and
   `/browser/submit` require this authorization to match the current capture/PASS/portrait.
5. Stale in-flight provider results are never promoted: before writing a canonical decision the
   transaction lock is reacquired, the current capture identity is recomputed, and a mismatch
   yields a safe `STALE_EVALUATION`/conflict instead of a PASS.
6. Provider calls are single-flight per identity (claim file) and provider failures are cached per
   identity (fail closed), so React StrictMode/re-renders/concurrent requests cannot multiply Groq
   calls for the same capture.

**Status:** Fixed

---

## 14. Browser + connectivity preflight on /capture and /xbiz/live_photo

**Milestone:** pre-M6
**Type:** Feature / Behavior
**What it does:**
Before ANY camera permission is requested, both capture journeys run a reusable gate
(`frontend/src/features/connectivity/`):

1. **Browser capability preflight** — feature detection of the exact APIs the current capture/quality
   pipeline uses (`window.isSecureContext`, `navigator.mediaDevices.getUserMedia`,
   `HTMLCanvasElement.getContext` + `canvas.toBlob`, `Blob`, `URL.createObjectURL` /
   `URL.revokeObjectURL`, `window.requestAnimationFrame`). Never user-agent sniffing.
2. **Backend reachability** — `GET /api/v1/info` through the normal API client with a short
   (~4s) timeout. A cached success is never accepted as proof of connectivity.

The journey only starts when both pass. `navigator.onLine` alone is never sufficient.

**Startup states:** `CHECKING` -> `READY` | `OFFLINE` | `BACKEND_UNREACHABLE` | `UNSUPPORTED`.

**Mid-session loss:** an `offline`/`online` event shows a blocking overlay while the mounted journey
(capture/transaction state, camera) is preserved. Recovery requires a real `/api/v1/info` success.

**Status:** Implemented

---

## 15. navigator.onLine is only a hint; backend reachability is authoritative

**Milestone:** pre-M6
**Type:** Behavior
**Why:** `navigator.onLine` is a browser-level hint (it can be wrong, and a browser can be online
while the LivePhoto backend, tunnel, or network path is down). The gate therefore:

- treats `navigator.onLine === false` as a fast-path to the offline screen (no pointless probe),
- NEVER treats the browser `online` event as recovery — it only triggers a fresh backend probe,
- considers the backend reachable only when `GET /api/v1/info` actually succeeds.

**Status:** Implemented

---

## 16. "Backend unavailable" vs "no internet connection"

**Milestone:** pre-M6
**Type:** Behavior
**Distinction:**

- **Offline** (browser reports offline): `No internet connection` / `Connect to the internet to continue.`
- **Backend unreachable** (browser online, `/api/v1/info` fails): `We can't connect right now.` /
  `Check your internet connection and try again.`

The backend-unreachable screen never exposes the HTTP status, backend URL, Cloudflare, exception,
or stack trace. Application-level responses (e.g. `401/403`/expired launch from a reachable backend)
are NOT connectivity errors and continue through their normal session error handling.

**Status:** Implemented

---

## 17. Supported-browser policy and unsupported-browser behavior

**Milestone:** pre-M6
**Type:** Policy
**Policy:** capability-driven support, not version lists. TARGET browser families:

- current/latest Google Chrome (desktop + Android)
- current/latest Microsoft Edge
- current/latest Firefox
- current/latest Safari (desktop + iOS Safari)

**Validated status:** connectivity preflight is exercised across Chromium, Firefox and WebKit.
The full camera journey is validated where tests/devices actually passed: camera-dependent automated
coverage is green on Chromium (synthetic camera); Firefox/WebKit camera-dependent Playwright coverage
remains limited by the test environment. Physical Android Chrome and iPhone/iOS Safari validation is
required before any UAT compatibility signoff — do not assume Firefox/WebKit gaps are purely
Playwright limitations until physical-device validation confirms that. See
`docs/CAMERA_COMPATIBILITY_MATRIX.md`.

**Unsupported behavior:** if the capability preflight fails, LivePhoto shows `Browser not supported`
with `Please use an updated version of Chrome, Edge, Firefox, or Safari.` and does NOT request the
camera. `INSECURE_CONTEXT` keeps its distinct message (`Camera requires a secure connection` /
`Use HTTPS to open LivePhoto.`). No large polyfill bundles are shipped to support obsolete browsers;
incompatible embedded WebViews fail gracefully.

**Status:** Implemented

---

## 18. Cold-start offline limitation (no service worker by design)

**Milestone:** pre-M6
**Type:** Known limitation
**Limitation:** if the LivePhoto URL is opened for the FIRST time while completely offline, the
frontend HTML/JS cannot load, so the React offline screen cannot be shown — the browser shows its
native offline page. Once the app JS has loaded, LivePhoto detects connectivity loss and shows its
own UI.

**Deliberate:** no service worker/PWA cache is added in this task. Offline caching/service workers in
a banking flow require a separate security/design decision.

**Status:** Known limitation (documented, not "fixed")

---

## 19. Mobile / Cloudflare connectivity testing

**Milestone:** pre-M6
**Type:** Manual testing
**Steps (phone + Cloudflare):**

1. Start backend (`backend/`) and frontend (`frontend/`) with `VITE_API_BASE_URL=` (empty). Vite
   proxies `/api` to the backend locally.
2. Expose the frontend over the tunnel:

   ```
   cloudflared tunnel --url http://localhost:5173
   ```

3. Open the tunnel URL on the phone.
4. Turn Wi-Fi/mobile data OFF: the app should show the connection-lost/offline state and start no
   new server actions.
5. Turn the network back ON: the app must run a real backend probe before the journey resumes.
6. Continue the capture normally.

Note: the earlier portrait `500` seen through Cloudflare was NOT a Cloudflare issue — it reproduced
locally and was the mobile `720x1280` passport-crop bug (section 13), now fixed. Do not change
Cloudflare/CORS settings for it.

**Status:** Manual steps provided; physical-device validation still required before UAT
(Android Chrome, iPhone/iOS Safari).

---

## 20. Browser update required (minimum supported version policy)

**Milestone:** pre-M6
**Type:** Feature / Policy
**What it does:**
The connectivity gate now enforces a backend-owned minimum supported browser version. A single
`GET /api/v1/info` probe (cache: no-store) returns BOTH backend reachability AND the browser
policy; the frontend detects the browser family + major version and evaluates it against the
policy before the journey can start.

**Policy location and reload semantics:**
- File: `backend/config/browser-support.json` (committed, provisional values; e.g. chrome 120,
  safari 17).
- Loaded ONCE at backend startup. Changing the file requires a backend restart / pod rollout (no
  ad-hoc hot reload). Later the JSON can be supplied via a Kubernetes ConfigMap without code
  changes.
- `/api/v1/info` serves `browser_policy` (safe fields only; never filesystem paths or secrets).

**Customer states:**
- Below minimum -> "Browser update required" / "Please update your browser to continue." +
  **Check again** (re-fetches fresh /info, redetects, reruns capabilities/connectivity). No
  "Continue anyway".
- Unknown family -> "Browser not supported".
- Recognized family, unparseable version -> "Browser update required" with
  "We couldn't verify that this browser version is supported…" (raw user-agent is never shown).
- Policy missing/unavailable -> fail closed with the same "couldn't verify" block.

**iOS / shells:** iOS environments (incl. Chrome/Firefox/Edge on iOS) map to the `ios_safari`
policy using the iOS OS version. Firefox-on-Android, Samsung Internet, Opera and Vivaldi are not in
the current policy families and fail closed as "Browser not supported".

**SECURITY NOTE:** version detection is a compatibility gate, NOT a security boundary. It is
spoofable and never affects liveness/PASS/portrait/fraud/callback security.

**Simulating the block locally (no old browser needed):**
1. Open `backend/config/browser-support.json`.
2. Temporarily raise a browser's `minimum_major` above the running browser (e.g. current Chrome 140
   -> set `chrome.minimum_major` to 141).
3. Restart the backend, reload the frontend -> "Browser update required".
4. Restore the minimum to <= the running version, restart the backend, press Check again -> flow
   proceeds.

**Status:** Implemented (provisional minima; physical UAT browser/device validation still required
to certify final versions).

---

## 21. Backend single-person (subject_count) enforcement

**Milestone:** pre-M6
**Type:** Feature / Security hardening (defense-in-depth)
**Why:** Real captures with two people (side-by-side, second face behind a shoulder, touching
bodies, second person near the frame edge) could reach portrait processing because MODNet portrait
matting is not person-instance segmentation — overlapping/touching people can both be preserved in
the matte. A multiple-person capture is a **capture-quality failure → RETRY**, not fraud.

**Authoritative rule:** canonical PASS is written ONLY when the backend VLM returns
`classification == LIVE` AND `subject_count == ONE`. `LIVE` + `MULTIPLE`/`ZERO`/`UNCERTAIN`/missing
`subject_count` -> RETRY, `portrait_allowed=false`, no PASS. Missing data is never defaulted to ONE.

**Enforcement points:**
- `POST /api/v1/browser/liveness` — writes a RETRY decision (never PASS) for MULTIPLE.
- `POST /api/v1/browser/portrait` and `POST /api/v1/browser/submit` — blocked by the current-PASS
  binding (no PASS exists after MULTIPLE).
- Standalone `POST /api/v1/transactions/{id}/portrait` — requires a persisted LIVE + ONE result
  (`vlm/result.json`), so MULTIPLE/UNCERTAIN never enter portrait processing even though the
  classification field is LIVE.

**Customer surface:** safe reason code `MULTIPLE_FACES` only; frontend maps it to "Make sure only
one person is visible." VLM/Groq/model/confidence/prompt are never exposed.

**Persistence:** `subject_count` is stored in `liveness/<identity>.json`, `vlm/result.json` and the
canonical decision metadata, bound to the same attempt_id / selected_sha256 / liveness_identity.

**Schema/version:** the normalized VLM schema is now `vlm-result-v2` with a REQUIRED
`subject_count`; a missing/invalid value is a schema failure (fail closed). Prompt is
`vlm-passive-v2` and instructs the model to inspect the whole image (sides, background, partially
occluded areas) and never to ignore a second person merely because the primary subject is dominant.

**Deterministic test behaviors (mock provider, local/test/dev only):**
`live` (ONE) | `live_multiple` | `live_zero` | `live_subject_uncertain` | plus
`mock_subject_count` provider override.

**Status:** Implemented (authoritative backend gate); accuracy on real multi-person captures is
validated only by the manual mobile/laptop test plan, not by synthetic tests.
