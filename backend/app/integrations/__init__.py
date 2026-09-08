"""Bank / consumer integration boundary (M5.8 Secure Consumer Integration).

Trust separation (kept by design):
- **S2S Integration API** (launch / reissue / status): callers are the authenticated
  consuming-application backend (JWT via ``S2S_AUTH_MODE=jwt``, or ``local_dev`` only in
  local/test/development).
- **Browser API**: callers are the customer browser holding an opaque HttpOnly session cookie + a
  session-bound CSRF cookie. The browser never receives bank server credentials.
- **Callback**: LivePhoto pushes to the consumer callback URL resolved from the trusted consumer
  profile (bearer_env / none), with a stable idempotency ``event_id``.

M5.8 implements the launch, redemption, browser-session, capture-attempt, canonical-PASS, submit and
callback flows. No M6 spoof work is included.
"""

from app.integrations.consumers import (
    CallbackConfig,
    ConsumerConfigError,
    ConsumerProfile,
    ConsumerRegistry,
    RequestPolicy,
    load_consumer_profiles,
)
from app.integrations.store import (
    IntegrationIndexError,
    IntegrationIndexPathError,
    IntegrationIndexStore,
    external_key_hash,
)

__all__ = [
    "CallbackConfig",
    "ConsumerConfigError",
    "ConsumerProfile",
    "ConsumerRegistry",
    "IntegrationIndexError",
    "IntegrationIndexPathError",
    "IntegrationIndexStore",
    "RequestPolicy",
    "external_key_hash",
    "load_consumer_profiles",
]
