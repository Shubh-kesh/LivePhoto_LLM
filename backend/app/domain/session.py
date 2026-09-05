"""Session lifecycle state (M1 §24, §68).

Session state is deliberately distinct from the liveness decision outcome (see
``app/domain/decision.py``). A session moves through capture/validation states and terminates in
one of the terminal states; ``RETRY`` is a *transient* session state that routes back toward
capture, while ``DecisionOutcome.RETRY`` is a decision outcome the bank acts on.

Conceptual transition model (documented only; transitions are implemented in a later milestone):

    CREATED
       |
       v
    ACTIVE
       |
       v
    CAPTURE_IN_PROGRESS
       |
       v
    VALIDATING
       |
       +--> PASS
       +--> RETRY --> ACTIVE
       +--> REVIEW
       +--> FAIL

    CREATED/ACTIVE may also:
       +--> EXPIRED
       +--> CANCELLED

Any transition that needs an enum value not listed here must be added deliberately; arbitrary
string status values are not permitted (M1 §24).
"""

from __future__ import annotations

import enum


class SessionState(enum.StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    CAPTURE_IN_PROGRESS = "CAPTURE_IN_PROGRESS"
    VALIDATING = "VALIDATING"
    PASS = "PASS"
    RETRY = "RETRY"
    REVIEW = "REVIEW"
    FAIL = "FAIL"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


#: States in which a session can no longer change.
TERMINAL_SESSION_STATES: frozenset[SessionState] = frozenset(
    {
        SessionState.PASS,
        SessionState.REVIEW,
        SessionState.FAIL,
        SessionState.EXPIRED,
        SessionState.CANCELLED,
    }
)

#: States in which a session is still progressing through the journey.
NON_TERMINAL_SESSION_STATES: frozenset[SessionState] = frozenset(
    {
        SessionState.CREATED,
        SessionState.ACTIVE,
        SessionState.CAPTURE_IN_PROGRESS,
        SessionState.VALIDATING,
        SessionState.RETRY,
    }
)


def is_terminal_session_state(state: SessionState) -> bool:
    return state in TERMINAL_SESSION_STATES
