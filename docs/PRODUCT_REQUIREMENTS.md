# LivePhoto — Product Requirements (M0 Baseline)

| | |
|---|---|
| Document status | Baseline for M0 |
| Applies to | LivePhoto V1 (initial production scope) |
| Owner | Architecture Working Group |
| Last updated | M0 |

---

## 1. Problem statement

When a bank customer opens an account or performs a high-value action remotely, the bank needs
reasonable assurance that the person capturing a photograph through their device is a **real human
physically present in front of the camera at capture time** — not a photograph, printout, screen
replay, or other presentation of a static image.

Banks in India increasingly rely on remote, device-based journeys. A spoofable capture step becomes
a systemic fraud enabler if the *liveness decision* is made by the browser or by a naive single
signal. LivePhoto is a **passive liveness / presentation-attack detection (PAD) component** that
answers one question only:

> Is the photograph being captured from a real human physically present in front of the camera at
> capture time?

LivePhoto is **not** an identity-matching system.

## 2. Business goal

Provide a bank-integrated, camera-capture-only, browser-based passive liveness service that:

- Returns an authoritative, server-side decision (`PASS / RETRY / REVIEW / FAIL`) with traceable
  reason codes.
- Achieves the strongest practically measurable spoof rejection for the Phase-1 attack scope
  (Section 5), with attack-specific false-acceptance measured explicitly.
- Completes capture→decision in **under 5 seconds** at initial load (≈20,000 transactions/day).
- Is architected so that detection can be strengthened (active liveness, dedicated PAD, temporal
  signals) without a customer-experience or integration rewrite.

## 3. Users

| Role | Relationship to LivePhoto |
|---|---|
| Bank customer (end user) | Browser-based capture; sees guidance, capture UI, outcome / return to bank |
| Bank backend | Initiates sessions; receives authoritative results (S2S) |
| Bank application UI | Redirects customer into and out of LivePhoto |
| LivePhoto operator / SRE | Runs the service |
| Fraud / model team | Reviews REVIEW cases, monitors metrics, tunes thresholds/models |
| Manual reviewer (future, M13) | Reviews cases escalated to REVIEW |

## 4. Bank integration model

```
Bank Application UI
        |
        v
Bank Backend
        |
        | Create LivePhoto session (authenticated S2S)
        v
LivePhoto Backend
        |
        | Return short-lived capture session (opaque token/URL)
        v
Bank Application redirects customer
        |
        v
LivePhoto UI  (camera capture, client-side UX guidance only)
        |
        | Camera capture burst -> server validation
        v
LivePhoto Backend (authoritative decision, persistence)
        |
        | server-to-server callback/result
        v
Bank Backend
        |
        v
LivePhoto UI redirects customer back to allow-listed bank return URL
        |
        v
Bank Application UI
```

**Contractual rule:** the browser is never the authoritative source of the liveness decision.
The bank must retrieve (result API) or receive (callback) the authoritative decision from the
LivePhoto backend. See `API_CONTRACT.md`.

## 5. Scope — V1 (Phase-1 attacks)

Initial implementation targets detection of, and differentiated reporting for:

1. Genuine live human.
2. Human photograph displayed on a mobile phone.
3. Human photograph displayed on a tablet.
4. Human photograph displayed on a laptop/monitor.
5. Printed human photograph.
6. Human photograph in newspaper.
7. Human photograph in magazine.
8. Blurred capture.
9. Extremely low-quality capture.
10. Multiple faces where only one is expected.
11. No face.
12. Strongly occluded face.
13. Poor lighting.
14. Excessively small/distant face.

The architecture must classify these **separately** wherever technically reasonable rather than
mapping every failure to `SPOOF`. Reason codes are the mechanism (see
`VALIDATION_PIPELINE.md`); candidate codes include:

```
NO_FACE
MULTIPLE_FACES
FACE_TOO_SMALL
BLURRED
UNDEREXPOSED
OVEREXPOSED
FACE_OCCLUDED
SCREEN_REPLAY_SUSPECTED
PRINT_ATTACK_SUSPECTED
IMAGE_QUALITY_FAILED
PASSIVE_PAD_FAILED
UNCERTAIN
```

Names are not final; the semantics and the requirement that they are deterministic application
concepts *are* final.

### Constraints for V1

- **Camera capture only.** Gallery upload / file upload is **disabled** in the initial
  implementation.
- **Passive liveness only.** The customer is *not* asked to blink on command, smile, turn the
  head, move closer, speak, read numbers, or record a video.
- **Photo-based experience.** No full video is stored by the product design (burst frames only).

## 6. Non-scope (V1, and generally)

- Face matching in any form: LivePhoto face ↔ Aadhaar / PAN / CKYC / existing customer image are
  all **out of scope**. LivePhoto is a PAD/liveness component, not an identity matcher.
- Active liveness challenges — **architecturally reserved** (see `ROADMAP.md` M23, `ADR-001`).
- Gallery upload.
- Multi-tenancy (see §12).
- Everything in the deferred attack scope (Section 7).

## 7. Deferred attack scope (documented now, not implemented in V1)

Future defence (separated by category in `THREAT_MODEL.md`):

- **Presentation attacks (advanced):** replayed video on mobile/laptop; high-resolution OLED
  displays; curved/bent prints; cut-eye attacks; paper/partial/3D/silicone masks.
- **Digital injection:** virtual camera, OBS, ManyCam, prerecorded-media injection, camera stream
  injection, camera API hooking, AI-generated faces / deepfake video.
- **Client/browser manipulation:** DevTools tampering, browser-API spoofing.
- **Backend/API abuse:** API manipulation, forged callbacks.
- **Operational/insider:** rooted/jailbroken device and emulator attacks are primarily device-side;
  insider misuse is handled by governance + audit.

Do **not** collapse these into one undifferentiated "SPOOF" bucket. They are documented as distinct
future threat categories so later controls and metrics can be attributed correctly.

## 8. Capture journey (V1 concept)

```
Camera open (permission requested)
   |
Face alignment (client-side UX guidance)
   |
Capture short burst            [configurable: 6-12 frames, ~1-2 s]
   |
Lightweight client-side quality screening (UX only, never authoritative)
   |
Upload candidate frames to server
   |
Server: face/quality/screen/PAD/VLM validation (authoritative)
   |
Decision PASS | RETRY | REVIEW | FAIL
   |
Preview of the single final photograph
   |
Redirect to approved bank return URL
```

Design rationale for burst-over-single-frame is captured in `ADR-002` and detailed in
`VALIDATION_PIPELINE.md`.

## 9. Decision outcomes (customer-facing semantics)

| Outcome | Meaning | Typical UX |
|---|---|---|
| **PASS** | Evidence strongly supports a genuine live user | Proceed / preview photo / return to bank |
| **RETRY** | Capture may be valid, but image/environment quality prevents reliable evaluation (blur, low light, face too small, temporary occlusion, poor framing) | Guided recapture (limited, configurable attempts) |
| **REVIEW** | Conflicting or suspicious evidence; business policy permits manual review | Return to bank; case escalated to reviewer (M13) |
| **FAIL** | Strong evidence of presentation attack, tampering, invalid session, repeated prohibited behaviour, or unrecoverable security failure | Stop; return to bank with failure |

Thresholds are **not** fixed in M0. They are versioned, configurable operating points evaluated in
M5/M9 (`MODEL_EVALUATION_STRATEGY.md`). Precise semantics per outcome: `ARCHITECTURE_PRINCIPLES.md`.

## 10. Success criteria (measurable)

The following define V1 product success. **No "100% accuracy" claim is made or accepted.** See
`MODEL_EVALUATION_STRATEGY.md` for the full metric set. At minimum:

- Attack-specific spoof false-acceptance (e.g., APCER) reported **separately per attack category**,
  never hidden inside aggregate accuracy.
- True-live accept and false-live-reject (BPCER) reported against production-representative live
  distribution.
- p95 capture→decision latency < 5 s with target p95 < 4 s.
- Every validator emits normalized, observable results (score/threshold/version/latency).
- Decisions are reproducible from recorded versions (model, prompt, threshold, config).

## 11. Manual review (conceptual only, M0)

Manual review is represented in the architecture (state flow, entities, data exposure) but the UI
and workflow are implemented in M13. See `DATA_MODEL.md` (`ReviewCase`) and `ROADMAP.md`.

## 12. Future capabilities (documented, not built)

- Active liveness (M23) on top of the same session/capture pipeline.
- Temporal liveness signals reusing burst frames (micro-motion, landmark consistency, illumination
  variation, reflection changes, screen-texture consistency, moiré changes, depth consistency).
- Multi-tenancy (future; avoid hardcoding bank name; keep tenant separation possible).
- Ensemble decision engine (M8).

## 13. Known limitations (V1)

- Passive liveness on a photo of a face cannot be defeated with certainty against every conceivable
  high-fidelity reproduction; the design maximizes practical protection and *measures* residual
  risk per attack class rather than asserting it away.
- Client-side checks can be bypassed — they are UX only.
- External VLM providers are POC-only for approved, non-sensitive demo images; production inference
  is targeted to self-hosted models inside bank-controlled infrastructure.
- Browser/device variety is wide (Android/iOS browsers, WebViews where feasible, laptops); capture
  quality variance is expected and handled via RETRY/quality gates.

## 14. Geographic scope

India only for initial applicability. Production assumptions: Indian banking environment, data
residency, bank security review, controlled biometric handling, audit and retention. **No legal
compliance is claimed automatically**; all regulatory/legal items are flagged for
bank compliance/legal/security confirmation (see `DATA_GOVERNANCE.md` and `SYSTEM_CONTEXT.md` open
questions).
