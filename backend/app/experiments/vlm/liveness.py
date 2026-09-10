"""Server-authoritative liveness evaluation for a stored capture (pre-M6 Groq gate).

The authoritative provider comes ONLY from backend configuration (``VLM_PROVIDER``); the browser
never chooses it. The provider pipeline (prompt, normalization, logging, metrics) is the existing
``VlmEvaluationService``.

Security/idempotency invariants (pre-M6 hardening):
- The evaluation identity is derived SERVER-SIDE from the stored capture metadata
  (``capture/capture.json``: attempt_id + selected-original SHA-256). The client cannot change it.
- A NEW capture invalidates prior authorization (decision/portrait/VLM result removed) atomically
  under the per-transaction lock in the caller.
- Canonical decisions and portraits are BOUND to the specific capture (attempt_id + SHA + identity)
  that produced them; a stale PASS/portrait can never authorize a different capture.
- Provider evaluation is single-flight per identity: concurrent requests for the same capture share
  one provider call (claim file). Provider failures are cached per identity (fail closed).

Classification + secondary_person_state -> decision mapping (pre-M6):
- LIVE + secondary_person_state NONE/BACKGROUND       -> PASS -> portrait allowed
- LIVE + secondary_person_state INTERFERING           -> RETRY (reason MULTIPLE_FACES)
- LIVE + secondary_person_state UNCERTAIN/missing     -> RETRY -> portrait forbidden
- LIVE + subject_count ZERO                           -> RETRY (reason NO_FACE)
- SCREEN_REPLAY / PRINT_ATTACK                        -> FAIL (person state does not override)
- QUALITY_FAILURE / UNCERTAIN                         -> RETRY
- missing/invalid secondary_person_state on a LIVE result -> fail closed (RETRY; never default NONE)
- provider/network/schema error -> no PASS, portrait forbidden (fail closed)

`subject_count` is retained for evidence/diagnostics but is NOT the authoritative multi-person
blocker: a clearly distant/background second person (subject_count MULTIPLE + secondary_person_state
BACKGROUND) must still PASS so portrait matting can remove the background person. Frontend
MULTIPLE_FACES is an early UX check only; the authoritative VLM `secondary_person_state` is the
defense-in-depth gate before any canonical PASS.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.decision import DecisionOutcome
from app.experiments.vlm.service import ExperimentEvaluateRequest, VlmEvaluationService
from app.providers.vision import PROMPT_VERSION, VLM_SCHEMA_VERSION
from app.providers.vision.models import ImageInput, SecondaryPersonState, SubjectCount
from app.transactions import ArtifactType
from app.transactions.decisions import read_decision
from app.transactions.store import TransactionFileStore, TransactionStatus

logger = get_logger("livephoto.liveness")

#: Person-state pairs the model may legitimately produce. Any pair outside this set is
#: contradictory (e.g. ONE + BACKGROUND) and fails closed. Never default/repair silently.
COHERENT_PERSON_STATES: frozenset[tuple[str, str]] = frozenset(
    {
        ("ZERO", "NONE"),
        ("ONE", "NONE"),
        ("MULTIPLE", "BACKGROUND"),
        ("MULTIPLE", "INTERFERING"),
        ("MULTIPLE", "UNCERTAIN"),
        ("UNCERTAIN", "UNCERTAIN"),
    }
)

#: Coherent pairs that may authorize a portrait (a single primary subject, or a distant
#: non-interfering background person removable by matting).
PORTRAIT_ELIGIBLE_PERSON_STATES: frozenset[tuple[str, str]] = frozenset(
    {
        ("ONE", "NONE"),
        ("MULTIPLE", "BACKGROUND"),
    }
)

#: Stable policy/version identifiers for authoritative VLM decisions.
LIVENESS_DECISION_SOURCE = "vlm"
#: v3: canonical PASS requires LIVE + a coherent, portrait-eligible person-state pair.
LIVENESS_DECISION_VERSION = "liveness-v3"

#: Transaction-relative paths.
LIVENESS_RELATIVE_DIR = "liveness"
DECISION_RELATIVE_PATH = "decisions/decision.json"
PORTRAIT_AUTHORIZATION_RELATIVE_PATH = "portrait/authorization.json"
CAPTURE_META_RELATIVE_PATH = "capture/capture.json"
VLM_RESULT_RELATIVE_PATH = "vlm/result.json"
PORTRAIT_RELATIVE_PATH = "portrait/processed.jpg"

#: Artifacts invalidated (removed) whenever a new capture supersedes the previous one.
AUTHORIZATION_ARTIFACTS: tuple[str, ...] = (
    DECISION_RELATIVE_PATH,
    PORTRAIT_RELATIVE_PATH,
    "portrait/processing.json",
    PORTRAIT_AUTHORIZATION_RELATIVE_PATH,
    VLM_RESULT_RELATIVE_PATH,
)


def liveness_identity(attempt_id: str | None, selected_sha256: str) -> str:
    """Deterministic evaluation identity: (attempt_id, selected-original SHA-256)."""
    raw = f"{attempt_id or ''}:{selected_sha256}".encode()
    return hashlib.sha256(raw).hexdigest()


def is_person_state_consistent(
    subject_count: str | None, secondary_person_state: str | None
) -> bool:
    """True only for a coherent (subject_count, secondary_person_state) pair.

    ``subject_count`` and ``secondary_person_state`` are independent model outputs and can
    contradict each other. Contradictory pairs (e.g. ONE + BACKGROUND) fail closed: they are never
    repaired or defaulted.
    """
    if subject_count is None or secondary_person_state is None:
        return False
    return (subject_count, secondary_person_state) in COHERENT_PERSON_STATES


def is_portrait_eligible_vlm_result(
    classification: str | None,
    subject_count: str | None,
    secondary_person_state: str | None,
) -> bool:
    """THE single authoritative person-state rule (used at every authorization boundary).

    Eligible for canonical PASS / portrait ONLY when:
    - classification == LIVE, AND
    - the person-state pair is coherent, AND
    - the pair is portrait-eligible: ONE+NONE or MULTIPLE+BACKGROUND (distant background person).
    """
    if classification != "LIVE":
        return False
    if not is_person_state_consistent(subject_count, secondary_person_state):
        return False
    return (subject_count, secondary_person_state) in PORTRAIT_ELIGIBLE_PERSON_STATES


def map_classification_to_outcome(
    classification: str | None,
    subject_count: str | None,
    secondary_person_state: str | None,
) -> DecisionOutcome:
    """Map normalized VLM classification + person state to a decision outcome.

    PASS uses the single authoritative ``is_portrait_eligible_vlm_result`` helper. Attacks FAIL
    regardless of person state. Everything else fails closed to RETRY (never default missing or
    contradictory person state).
    """
    if classification in ("SCREEN_REPLAY", "PRINT_ATTACK"):
        # Person state does not override an attack FAIL.
        return DecisionOutcome.FAIL
    if is_portrait_eligible_vlm_result(classification, subject_count, secondary_person_state):
        return DecisionOutcome.PASS
    return DecisionOutcome.RETRY


def interference_reasons(
    subject_count: str | None, secondary_person_state: str | None
) -> list[str]:
    """Safe retry reason codes derived from the normalized person state.

    Never raw VLM/model output; always the stable application reason vocabulary.
    """
    if subject_count == "ZERO":
        return ["NO_FACE"]
    if secondary_person_state == "INTERFERING":
        return ["MULTIPLE_FACES"]
    return []


def portrait_allowed(outcome: DecisionOutcome) -> bool:
    return outcome == DecisionOutcome.PASS


# --------------------------------------------------------------------- capture
def current_capture_key(store: TransactionFileStore, transaction_id: str) -> dict[str, str] | None:
    """Server-authoritative current capture identity from ``capture/capture.json``."""
    if not store.artifact_exists(transaction_id, CAPTURE_META_RELATIVE_PATH):
        return None
    try:
        meta = store.read_json(transaction_id, CAPTURE_META_RELATIVE_PATH)
        sha = str(meta.get("sha256", ""))
        if not sha:
            return None
        return {
            "attempt_id": str(meta.get("attempt_id", "")),
            "selected_sha256": sha,
        }
    except Exception:
        return None


def expected_liveness_identity(store: TransactionFileStore, transaction_id: str) -> str | None:
    key = current_capture_key(store, transaction_id)
    if key is None:
        return None
    return liveness_identity(key["attempt_id"], key["selected_sha256"])


def invalidate_authorization(store: TransactionFileStore, transaction_id: str) -> None:
    """Remove prior authorization artifacts so a stale PASS/portrait/VLM result cannot authorize a
    new capture. Caller holds the per-transaction lock."""
    for relative in AUTHORIZATION_ARTIFACTS:
        if store.artifact_exists(transaction_id, relative):
            try:
                store.remove_artifact(transaction_id, relative)
            except Exception:  # pragma: no cover - defensive
                logger.warning(
                    "invalidate_artifact_failed", transaction_id=transaction_id, path=relative
                )


# --------------------------------------------------------------- single-flight
# Claim files are per-identity and carry a started_at timestamp so a crashed/stale claim (e.g. a
# worker died mid-provider-call) can be recovered after a bounded duration derived from the existing
# VLM timeout/retry settings — no new environment variable.
EVALUATION_CLAIM_PREFIX = "claim"
PORTRAIT_CLAIM_PREFIX = "portrait-claim"


def claim_path_for(identity: str, prefix: str) -> str:
    return f"{LIVENESS_RELATIVE_DIR}/{prefix}-{identity}.json"


def claim_timeout_seconds(settings: Settings) -> float:
    """Bounded claim lifetime: total worst-case provider latency (timeout + retries) plus buffer."""
    return settings.vlm_timeout_seconds * (settings.vlm_max_retries + 2) + 10.0


def claim_is_stale(settings: Settings, claim: dict[str, Any]) -> bool:
    try:
        started = datetime.datetime.fromisoformat(str(claim.get("started_at", "")))
    except (TypeError, ValueError):
        return True  # malformed claim -> treat as stale
    age = (datetime.datetime.now(datetime.UTC) - started).total_seconds()
    return age > claim_timeout_seconds(settings)


def read_claim(
    store: TransactionFileStore, transaction_id: str, identity: str, prefix: str
) -> dict[str, Any] | None:
    if not store.artifact_exists(transaction_id, claim_path_for(identity, prefix)):
        return None
    try:
        data = store.read_json(transaction_id, claim_path_for(identity, prefix))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def set_claim(store: TransactionFileStore, transaction_id: str, identity: str, prefix: str) -> None:
    store.write_json(
        transaction_id,
        claim_path_for(identity, prefix),
        {
            "identity": identity,
            "status": "IN_PROGRESS",
            "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
        },
    )


def clear_claim(
    store: TransactionFileStore, transaction_id: str, identity: str, prefix: str
) -> None:
    from contextlib import suppress

    with suppress(Exception):  # pragma: no cover - defensive
        store.remove_artifact(transaction_id, claim_path_for(identity, prefix))


def is_claimed(
    store: TransactionFileStore, transaction_id: str, identity: str, prefix: str
) -> bool:
    return store.artifact_exists(transaction_id, claim_path_for(identity, prefix))


def claim_ready(
    store: TransactionFileStore,
    transaction_id: str,
    identity: str,
    prefix: str,
    settings: Settings,
) -> bool:
    """True when a fresh claim may be established (no active claim, or the claim is stale)."""
    if not is_claimed(store, transaction_id, identity, prefix):
        return True
    claim = read_claim(store, transaction_id, identity, prefix)
    return claim is None or claim_is_stale(settings, claim)


# ---- evaluation (liveness) claims ----
def is_evaluation_claimed(store: TransactionFileStore, transaction_id: str, identity: str) -> bool:
    return is_claimed(store, transaction_id, identity, EVALUATION_CLAIM_PREFIX)


def set_evaluation_claim(store: TransactionFileStore, transaction_id: str, identity: str) -> None:
    set_claim(store, transaction_id, identity, EVALUATION_CLAIM_PREFIX)


def clear_evaluation_claim(store: TransactionFileStore, transaction_id: str, identity: str) -> None:
    clear_claim(store, transaction_id, identity, EVALUATION_CLAIM_PREFIX)


def evaluation_claim_ready(
    store: TransactionFileStore, transaction_id: str, identity: str, settings: Settings
) -> bool:
    return claim_ready(store, transaction_id, identity, EVALUATION_CLAIM_PREFIX, settings)


# ---- portrait claims ----
def is_portrait_claimed(store: TransactionFileStore, transaction_id: str, identity: str) -> bool:
    return is_claimed(store, transaction_id, identity, PORTRAIT_CLAIM_PREFIX)


def set_portrait_claim(store: TransactionFileStore, transaction_id: str, identity: str) -> None:
    set_claim(store, transaction_id, identity, PORTRAIT_CLAIM_PREFIX)


def clear_portrait_claim(store: TransactionFileStore, transaction_id: str, identity: str) -> None:
    clear_claim(store, transaction_id, identity, PORTRAIT_CLAIM_PREFIX)


def portrait_claim_ready(
    store: TransactionFileStore, transaction_id: str, identity: str, settings: Settings
) -> bool:
    return claim_ready(store, transaction_id, identity, PORTRAIT_CLAIM_PREFIX, settings)


# ------------------------------------------------------------- evaluation cache
def evaluation_relative_path(identity: str) -> str:
    return f"{LIVENESS_RELATIVE_DIR}/{identity}.json"


#: Valid normalized person categories for the current schema.
VALID_SUBJECT_COUNTS: frozenset[str] = frozenset(c.value for c in SubjectCount)
VALID_SECONDARY_STATES: frozenset[str] = frozenset(c.value for c in SecondaryPersonState)


def is_current_evaluation(payload: dict[str, Any] | None) -> bool:
    """True only when a cached liveness record matches the CURRENT evaluation contract.

    A cached record may be reused for authoritative promotion only when it was produced under the
    current schema/prompt contract with valid ``subject_count`` and ``secondary_person_state``.
    Legacy records (older schema/prompt, missing/invalid ``subject_count`` or
    ``secondary_person_state``) MUST NOT be reused: callers re-evaluate the same capture once with
    the current provider/schema. An old ``outcome=PASS`` is never treated as current authorization
    and a missing person state is never defaulted to NONE/BACKGROUND.

    Fail-closed error records are reusable (they never authorize PASS and preserve idempotent
    provider-error caching): a record with a truthy ``error`` is always fail-closed RETRY.
    """
    if payload is None:
        return False
    # Fail-closed provider/error records: reusable (never PASS), preserves error-cache idempotency.
    if payload.get("error"):
        return True
    if payload.get("schema_version") != VLM_SCHEMA_VERSION:
        return False
    if payload.get("prompt_version") != PROMPT_VERSION:
        return False
    subject_count = payload.get("subject_count")
    secondary_person_state = payload.get("secondary_person_state")
    if subject_count not in VALID_SUBJECT_COUNTS:
        return False
    if secondary_person_state not in VALID_SECONDARY_STATES:
        return False
    # The pair must be semantically coherent; an inconsistent v3 cache is never reused for PASS.
    return is_person_state_consistent(subject_count, secondary_person_state)


def read_evaluation(
    store: TransactionFileStore, transaction_id: str, identity: str
) -> dict[str, Any] | None:
    if not store.artifact_exists(transaction_id, evaluation_relative_path(identity)):
        return None
    try:
        data = store.read_json(transaction_id, evaluation_relative_path(identity))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def persist_evaluation(
    store: TransactionFileStore,
    transaction_id: str,
    identity: str,
    payload: dict[str, Any],
) -> None:
    store.write_json(transaction_id, evaluation_relative_path(identity), payload)


def persist_error_evaluation(
    store: TransactionFileStore,
    transaction_id: str,
    identity: str,
    *,
    attempt_id: str | None,
    selected_sha256: str,
    error_code: str,
) -> None:
    """Persist a fail-closed evaluation for a provider/schema error (cached so a repeat does not
    re-call the provider for the same capture)."""
    payload = _error_payload(
        error_code,
        attempt_id,
        selected_sha256,
        datetime.datetime.now(datetime.UTC).isoformat(),
        provider=None,
    )
    persist_evaluation(store, transaction_id, identity, payload)


# ------------------------------------------------------------- provider call
async def evaluate_capture(
    settings: Settings,
    store: TransactionFileStore,
    transaction_id: str,
    *,
    attempt_id: str | None,
    selected_sha256: str,
) -> dict[str, Any]:
    """Evaluate the stored capture with the configured provider. Never raises for provider errors.

    Returns a normalized payload (an ``error`` field is set on provider/schema failure so callers
    can cache fail-closed outcomes). Reads the stored artifact server-side.
    """
    provider_name = (settings.vlm_provider or "").lower()
    image_bytes = store.read_artifact(transaction_id, "capture/selected-original.jpg")
    mime = "image/jpeg"
    started_at = datetime.datetime.now(datetime.UTC).isoformat()

    if not provider_name:
        return _error_payload(
            "PROVIDER_NOT_CONFIGURED", attempt_id, selected_sha256, started_at, provider=None
        )

    # Deterministic test seam: mock-provider behavior is server-configured, never browser-chosen.
    mock_behavior = settings.vlm_mock_behavior if provider_name == "mock" else ""
    request = ExperimentEvaluateRequest(
        strategy="single-quality-v1",
        provider=provider_name,
        mock_behavior=mock_behavior,
        frames=[ImageInput(bytes=image_bytes, mime_type=mime, sequence=0)],
    )
    service = VlmEvaluationService(settings)
    result = await service.evaluate(request)

    if result.error is not None:
        return _error_payload(
            result.error.value,
            attempt_id,
            selected_sha256,
            started_at,
            provider=provider_name,
            model=result.model,
        )

    classification = result.classification
    subject_count = result.subject_count
    secondary_person_state = result.secondary_person_state
    outcome = map_classification_to_outcome(classification, subject_count, secondary_person_state)
    return {
        "attempt_id": attempt_id,
        "selected_sha256": selected_sha256,
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "schema_version": result.schema_version,
        "classification": classification,
        "attack_medium": result.attack_medium,
        "evidence_codes": list(result.evidence_codes),
        "subject_count": subject_count,
        "secondary_person_state": secondary_person_state,
        "reason_codes": interference_reasons(subject_count, secondary_person_state),
        "outcome": outcome.value,
        "portrait_allowed": portrait_allowed(outcome),
        "latency_ms": result.latency_ms,
        "error": None,
        "created_at": started_at,
    }


def _error_payload(
    error_code: str,
    attempt_id: str | None,
    selected_sha256: str,
    started_at: str,
    *,
    provider: str | None,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "selected_sha256": selected_sha256,
        "provider": provider,
        "model": model,
        "prompt_version": None,
        "schema_version": None,
        "classification": None,
        "attack_medium": None,
        "evidence_codes": [],
        "subject_count": None,
        "secondary_person_state": None,
        "reason_codes": [],
        "outcome": DecisionOutcome.RETRY.value,
        "portrait_allowed": False,
        "latency_ms": None,
        "error": error_code,
        "created_at": started_at,
    }


# --------------------------------------------------------------- current binding
def has_current_canonical_pass(store: TransactionFileStore, transaction_id: str) -> bool:
    """True only when the canonical decision is a PASS bound to the CURRENT stored capture.

    Verifies: decision exists, outcome PASS, authoritative VLM source, and metadata
    (attempt_id / selected_sha256 / liveness_identity) all equal the current capture.
    """
    decision = read_decision(store, transaction_id)
    if decision is None or decision.outcome != DecisionOutcome.PASS:
        return False
    if decision.decision_source != LIVENESS_DECISION_SOURCE:
        return False
    key = current_capture_key(store, transaction_id)
    if key is None:
        return False
    meta = decision.metadata or {}
    return (
        meta.get("attempt_id") == key["attempt_id"]
        and meta.get("selected_sha256") == key["selected_sha256"]
        and meta.get("liveness_identity")
        == liveness_identity(key["attempt_id"], key["selected_sha256"])
        # Defense in depth: the decision must carry the CURRENT schema and a COHERENT,
        # portrait-eligible person-state pair (same rule as live promotion). Legacy or
        # contradictory metadata (e.g. ZERO+NONE, MULTIPLE+INTERFERING) never authorizes.
        and meta.get("schema_version") == VLM_SCHEMA_VERSION
        and is_portrait_eligible_vlm_result(
            meta.get("classification"),
            meta.get("subject_count"),
            meta.get("secondary_person_state"),
        )
    )


def decision_metadata_for(evaluation: dict[str, Any], *, identity: str) -> dict[str, Any]:
    return {
        "attempt_id": evaluation.get("attempt_id"),
        "selected_sha256": evaluation.get("selected_sha256"),
        "liveness_identity": identity,
        "provider": evaluation.get("provider"),
        "model": evaluation.get("model"),
        "classification": evaluation.get("classification"),
        "subject_count": evaluation.get("subject_count"),
        "secondary_person_state": evaluation.get("secondary_person_state"),
        "prompt_version": evaluation.get("prompt_version"),
        "schema_version": evaluation.get("schema_version"),
    }


def portrait_authorization_path() -> str:
    return PORTRAIT_AUTHORIZATION_RELATIVE_PATH


def portrait_candidate_path(identity: str) -> str:
    """Identity-specific staging path; never written directly to portrait/processed.jpg."""
    return f"portrait/candidates/{identity}.jpg"


def capture_snapshot(store: TransactionFileStore, transaction_id: str) -> dict[str, Any] | None:
    """Snapshot the decision + capture identity that authorizes portrait generation.

    Requires a current canonical PASS bound to the current capture. Returns None otherwise. The
    snapshot is taken under the per-transaction lock BEFORE expensive processing so a stale portrait
    can be detected afterwards.
    """
    if not has_current_canonical_pass(store, transaction_id):
        return None
    decision = read_decision(store, transaction_id)
    key = current_capture_key(store, transaction_id)
    if decision is None or key is None:
        return None
    return {
        "decision_id": decision.decision_id,
        "attempt_id": key["attempt_id"],
        "selected_sha256": key["selected_sha256"],
        "liveness_identity": liveness_identity(key["attempt_id"], key["selected_sha256"]),
    }


def snapshot_matches_current(
    store: TransactionFileStore, transaction_id: str, snapshot: dict[str, Any]
) -> bool:
    """True only when the snapshot decision/capture is STILL the CURRENT decision/capture.

    Requires a current canonical PASS and an EXACT match of decision_id, attempt_id,
    selected_sha256 and liveness_identity.
    """
    if not has_current_canonical_pass(store, transaction_id):
        return False
    decision = read_decision(store, transaction_id)
    key = current_capture_key(store, transaction_id)
    if decision is None or key is None:
        return False
    identity = liveness_identity(key["attempt_id"], key["selected_sha256"])
    return (
        decision.decision_id == snapshot.get("decision_id")
        and key["attempt_id"] == snapshot.get("attempt_id")
        and key["selected_sha256"] == snapshot.get("selected_sha256")
        and identity == snapshot.get("liveness_identity")
    )


def write_portrait_authorization(
    store: TransactionFileStore,
    transaction_id: str,
    *,
    decision_id: str,
    attempt_id: str,
    selected_sha256: str,
    identity: str,
    portrait_sha256: str,
) -> None:
    store.write_json(
        transaction_id,
        PORTRAIT_AUTHORIZATION_RELATIVE_PATH,
        {
            "decision_id": decision_id,
            "attempt_id": attempt_id,
            "selected_sha256": selected_sha256,
            "liveness_identity": identity,
            "portrait_sha256": portrait_sha256,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        },
    )


def portrait_authorization_current(store: TransactionFileStore, transaction_id: str) -> bool:
    """True only when the stored processed portrait is authorized by the current PASS/capture.

    Verified against: current canonical PASS, current capture (attempt_id + SHA + identity), and
    the on-disk portrait SHA-256.
    """
    if not has_current_canonical_pass(store, transaction_id):
        return False
    if not store.artifact_exists(transaction_id, PORTRAIT_AUTHORIZATION_RELATIVE_PATH):
        return False
    try:
        auth = store.read_json(transaction_id, PORTRAIT_AUTHORIZATION_RELATIVE_PATH)
    except Exception:
        return False
    if not store.artifact_exists(transaction_id, PORTRAIT_RELATIVE_PATH):
        return False
    decision = read_decision(store, transaction_id)
    key = current_capture_key(store, transaction_id)
    if decision is None or key is None:
        return False
    expected_identity = liveness_identity(key["attempt_id"], key["selected_sha256"])
    actual_sha = _sha256_of_artifact(store, transaction_id, PORTRAIT_RELATIVE_PATH)
    return (
        auth.get("decision_id") == decision.decision_id
        and auth.get("attempt_id") == key["attempt_id"]
        and auth.get("selected_sha256") == key["selected_sha256"]
        and auth.get("liveness_identity") == expected_identity
        and auth.get("portrait_sha256") == actual_sha
    )


def _sha256_of_artifact(
    store: TransactionFileStore, transaction_id: str, relative_path: str
) -> str:
    data = store.read_artifact(transaction_id, relative_path)
    return hashlib.sha256(data).hexdigest()


def persist_normalized_vlm_result(
    store: TransactionFileStore,
    transaction_id: str,
    evaluation: dict[str, Any],
    *,
    request_id: str,
) -> None:
    """Persist the normalized VLM result to ``vlm/result.json`` (the /capture portrait gate).

    Safe metadata only: no credentials, raw provider text or image bytes.
    """
    store.write_artifact(
        transaction_id,
        ArtifactType.VLM_RESULT,
        json.dumps(
            {
                "provider": evaluation.get("provider"),
                "model": evaluation.get("model"),
                "strategy": "single-quality-v1",
                "classification": evaluation.get("classification"),
                "attack_medium": evaluation.get("attack_medium"),
                "self_reported_confidence": None,
                "evidence_codes": list(evaluation.get("evidence_codes", [])),
                "subject_count": evaluation.get("subject_count"),
                "secondary_person_state": evaluation.get("secondary_person_state"),
                "latency_ms": evaluation.get("latency_ms"),
                "request_id": request_id,
                "prompt_version": evaluation.get("prompt_version"),
                "schema_version": evaluation.get("schema_version"),
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "error": evaluation.get("error"),
            },
            sort_keys=True,
        ).encode("utf-8"),
        content_type="application/json",
    )
    store.update_transaction_status(transaction_id, TransactionStatus.VLM_EVALUATED.value)
