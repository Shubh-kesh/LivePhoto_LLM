"""Business domain concepts.

Domain code must not import FastAPI, SQLAlchemy, HTTP clients or cloud SDKs (M0 P73). M1 defines
only the contracts required by the foundation: session state, decision outcomes, reason codes and
the normalized validator result.
"""

from app.domain.decision import DecisionOutcome
from app.domain.reason import ReasonCode
from app.domain.session import (
    NON_TERMINAL_SESSION_STATES,
    TERMINAL_SESSION_STATES,
    SessionState,
    is_terminal_session_state,
)
from app.domain.validation import (
    ValidatorHealth,
    ValidatorResult,
    ValidatorResultStatus,
)

__all__ = [
    "NON_TERMINAL_SESSION_STATES",
    "TERMINAL_SESSION_STATES",
    "DecisionOutcome",
    "ReasonCode",
    "SessionState",
    "ValidatorHealth",
    "ValidatorResult",
    "ValidatorResultStatus",
    "is_terminal_session_state",
]
