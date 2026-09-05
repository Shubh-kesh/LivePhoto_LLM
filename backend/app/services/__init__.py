"""Application-use-case orchestration (M0 P4, M1 §9).

Future use cases (CreateSession, SubmitCapture, RunValidation, GetResult) live here. None are
implemented in M1. Services orchestrate domain concepts and validators and are the only layer that
may depend on validators/providers abstractions; HTTP routers stay thin (``app/api``).
"""
