"""HTTP API layer (M0 P14, M1 §9).

Routers only handle request parsing, response mapping and dependency injection — never business
logic. Business logic lives in ``app/services`` (future).
"""

from app.api.v1.routes import router as v1_router

__all__ = ["v1_router"]
