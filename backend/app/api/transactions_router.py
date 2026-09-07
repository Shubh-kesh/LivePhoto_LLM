"""Transaction API router aggregator (M5.7 §62-64)."""

from app.api.v1.transactions import router

__all__ = ["transactions_router"]

transactions_router = router
