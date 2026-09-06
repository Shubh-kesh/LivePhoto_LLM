"""Experiment API router aggregator (M4 §10)."""

from app.api.v1.experiments import router

__all__ = ["experiments_router"]

experiments_router = router
