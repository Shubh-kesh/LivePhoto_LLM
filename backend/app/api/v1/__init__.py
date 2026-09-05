"""Version 1 business API routes (M1 §22).

Exposed under ``/api/v1``. Only non-sensitive, foundation endpoints exist in M1.
"""

from app.api.v1.routes import router

__all__ = ["router"]
