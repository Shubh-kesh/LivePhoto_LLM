"""V1 API response schemas (Zod mirrors these client-side)."""

from __future__ import annotations

from pydantic import BaseModel

from app.core.browser_policy import BrowserSupportPolicy


class InfoResponse(BaseModel):
    """Non-sensitive application information exposed to any client.

    Never expose configuration dumps, credentials or internal details here (M0 API_CONTRACT §17).
    ``browser_policy`` carries only the safe minimum-supported-version policy; no filesystem
    paths, secrets or internal deployment information.
    """

    name: str
    version: str
    environment: str
    browser_policy: BrowserSupportPolicy | None = None
