"""Backend-owned browser support policy (pre-M6).

The minimum supported browser versions are operational configuration owned by the backend, not
hardcoded in React components and not environment-secret values. The committed
``config/browser-support.json`` holds PROVISIONAL compatibility baselines (not certification
claims). Later the file can be supplied by a Kubernetes ConfigMap without code changes.

Security note: this policy is a compatibility/supportability gate, NOT a security boundary.
Browser/version detection can be spoofed and must never influence liveness, PASS authorization,
portrait authorization, fraud decisions, or callback security.

Reload semantics: the policy is loaded once at application startup (see ``app/factory.py``).
Changing ``config/browser-support.json`` requires a backend restart / pod rollout. This is the
documented, predictable behaviour for pre-M6; no ad-hoc hot reload is implemented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

BrowserFamily = Literal[
    "chrome",
    "edge",
    "firefox",
    "safari",
    "ios_safari",
    "android_chrome",
]


class BrowserPolicyConfigError(Exception):
    """Raised when the browser-support policy file is missing, unparseable or invalid."""


class BrowserPolicyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Strict types: a malformed entry (string number, "yes"/"1" booleans) is rejected, never
    # silently coerced into a plausible-looking policy.
    minimum_major: int = Field(
        gt=0, strict=True, description="minimum supported major version (>=1)"
    )
    enabled: StrictBool


class BrowserPolicies(BaseModel):
    """Exactly the six known browser families; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    chrome: BrowserPolicyEntry
    edge: BrowserPolicyEntry
    firefox: BrowserPolicyEntry
    safari: BrowserPolicyEntry
    ios_safari: BrowserPolicyEntry
    android_chrome: BrowserPolicyEntry


class BrowserSupportPolicy(BaseModel):
    """Typed browser support policy, safe to expose via /api/v1/info.

    Only non-sensitive policy data is present: no filesystem paths, secrets or internal
    deployment information.
    """

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(min_length=1)
    browsers: BrowserPolicies


def load_browser_support_policy(path: str) -> BrowserSupportPolicy:
    """Load and validate the browser-support policy from a JSON file.

    Raises ``BrowserPolicyConfigError`` on missing/unparseable/invalid file so callers can fail
    closed. A malformed policy is never silently accepted.
    """
    config_path = Path(path)
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise BrowserPolicyConfigError(
            f"cannot read browser-support policy at '{path}': {exc}"
        ) from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BrowserPolicyConfigError(f"browser-support policy JSON is invalid: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BrowserPolicyConfigError("browser-support policy must be a JSON object")
    try:
        return BrowserSupportPolicy.model_validate(parsed)
    except ValidationError as exc:
        raise BrowserPolicyConfigError(f"browser-support policy is invalid: {exc}") from exc
