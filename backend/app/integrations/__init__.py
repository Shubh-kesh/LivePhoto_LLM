"""Bank integration boundary (M0 API_CONTRACT, M1 §23, §71).

Future server-to-server integration and decision callbacks live here. Nothing is implemented in M1.

Trust separation (kept by design):
- **Bank Integration API**: callers are the authenticated bank backend (mTLS / OAuth2 client
  credentials / signed requests — mechanism pending, open question #4).
- **Capture API**: callers are the customer browser holding only a short-lived opaque session
  credential. The browser must never receive bank server credentials.

Callback contract (M1 refinement of docs/API_CONTRACT.md): every outbound callback carries a stable
``event_id``, an ``event_type`` (e.g. ``LIVEPHOTO.DECISION.CREATED``), ``transaction_id`` and
``decision_id``, with idempotency, retry state, delivery attempts, acknowledgement and audit
history.
"""
