"""V1 API response schemas (Zod mirrors these client-side)."""

from __future__ import annotations

from pydantic import BaseModel


class InfoResponse(BaseModel):
    """Non-sensitive application information exposed to any client.

    Never expose configuration dumps, credentials or internal details here (M0 API_CONTRACT §17).
    """

    name: str
    version: str
    environment: str
