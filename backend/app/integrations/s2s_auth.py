"""S2S authentication for the consumer integration API (M5.8 §5, §9).

Two modes (``S2S_AUTH_MODE``):
- ``jwt``: verify an RS256 JWT against a JWKS (PyJWT / PyJWKClient). The configured identity claim
  (``S2S_JWT_CLIENT_ID_CLAIM``) is mapped to ``ConsumerProfile.jwt_client_ids``. We never assume
  ``sub == consumer_id``.
- ``local_dev``: constant-time comparison of ``X-LivePhoto-Dev-Auth`` against
  ``S2S_LOCAL_DEV_TOKEN``; only structurally possible when ``app_env`` is local/test/development
  (enforced at Settings load). The request ``source`` must name an active consumer profile.

Unconfigured mode (``""``) refuses all S2S requests (integration not configured).
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any

import jwt

from app.core.config import Settings
from app.integrations.consumers import ConsumerProfile, ConsumerRegistry


class S2SAuthError(Exception):
    """Typed S2S authentication/authorization failure."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


#: Process-wide PyJWKClient cache keyed by JWKS URL (avoids a network fetch per request and an
#: unauthenticated JWKS amplification vector).
_jwk_clients: dict[str, Any] = {}


def _jwk_client(url: str) -> Any:
    if url not in _jwk_clients:
        _jwk_clients[url] = jwt.PyJWKClient(url)
    return _jwk_clients[url]


def _decode_jwt(settings: Settings, token: str) -> dict[str, Any]:
    """Decode and verify a JWT against the configured JWKS (http(s) or local file).

    Passing ``audience``/``issuer`` enables the default aud/iss/exp/nbf signature verification.
    Any PyJWT failure (bad signature, unknown kid, JWKS network error, malformed JWKS) is treated as
    an invalid/unconfigured S2S token, never a 500.
    """
    try:
        if settings.s2s_jwks_is_local_path:
            content = Path(settings.s2s_jwt_jwks_url).read_bytes().decode("utf-8")
            key_set = jwt.PyJWKSet.from_json(content)
            kid = jwt.get_unverified_header(token).get("kid")
            jwk = next((k for k in key_set.keys if k.key_id == kid), None)
            if jwk is None:
                raise jwt.exceptions.InvalidKeyError("no matching JWK for token kid")
            key = jwk.key
        else:
            client = _jwk_client(settings.s2s_jwt_jwks_url)
            key = client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=list(settings.s2s_jwt_algorithms),
            audience=settings.s2s_jwt_audience,
            issuer=settings.s2s_jwt_issuer,
            leeway=settings.s2s_jwt_clock_skew_seconds,
        )
    except jwt.exceptions.PyJWTError as exc:
        raise S2SAuthError(
            code="UNAUTHORIZED", message="Invalid S2S token", status_code=401
        ) from exc
    except (OSError, ValueError) as exc:
        raise S2SAuthError(
            code="INTEGRATION_NOT_CONFIGURED",
            message="S2S authentication is not configured",
            status_code=503,
        ) from exc


def authenticate_s2s(
    settings: Settings,
    registry: ConsumerRegistry,
    *,
    authorization_header: str,
    dev_auth_header: str,
    requested_source: str,
) -> ConsumerProfile:
    """Authenticate the S2S caller and return the authorized active consumer profile.

    Raises ``S2SAuthError`` on any authentication/authorization failure. The request ``source``
    must match the authenticated consumer's ``consumer_id`` — an arbitrary source is never trusted.
    """
    if settings.s2s_auth_mode == "local_dev":
        expected = settings.s2s_local_dev_token.get_secret_value()
        if not expected or not hmac.compare_digest(dev_auth_header, expected):
            raise S2SAuthError(
                code="UNAUTHORIZED",
                message="Invalid local development credentials",
                status_code=401,
            )
        profile = registry.active_consumer(requested_source)
        if profile is None:
            raise S2SAuthError(
                code="FORBIDDEN",
                message="Unknown or inactive consumer",
                status_code=403,
            )
        return profile

    if settings.s2s_auth_mode == "jwt":
        if not authorization_header.lower().startswith("bearer "):
            raise S2SAuthError(code="UNAUTHORIZED", message="Missing bearer token", status_code=401)
        token = authorization_header[7:].strip()
        claims = _decode_jwt(settings, token)
        client_id = claims.get(settings.s2s_jwt_client_id_claim)
        if not isinstance(client_id, str) or not client_id:
            raise S2SAuthError(
                code="UNAUTHORIZED", message="Missing client identity claim", status_code=401
            )
        profile = registry.find_by_client_id(client_id)
        if profile is None or not profile.active:
            raise S2SAuthError(
                code="FORBIDDEN", message="Unknown or inactive consumer", status_code=403
            )
        # Source (when supplied) must match the identity-derived profile; never trust an arbitrary
        # source. When absent, the identity itself scopes the operation.
        if requested_source and requested_source != profile.consumer_id:
            raise S2SAuthError(
                code="FORBIDDEN", message="Source does not match consumer identity", status_code=403
            )
        return profile

    raise S2SAuthError(
        code="INTEGRATION_NOT_CONFIGURED",
        message="S2S integration is not configured",
        status_code=503,
    )
