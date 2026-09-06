"""Structured logging via structlog.

Rules (M0 OBSERVABILITY_STRATEGY):
- No raw biometric image bytes, access tokens, authorization headers, API keys or passwords.
- A key-based redaction processor is the safety net; middleware never logs header values by
  default and uses ``safe_headers`` when headers are logged.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import structlog

from app.core.config import Settings

#: Keys that must never appear verbatim in logs. Comparison is case-insensitive and
#: substring-triggered for token/secret/password families.
_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "passwd", "api_key", "apikey")
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "proxy-authorization",
        "x-goog-api-key",
    }
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _SENSITIVE_HEADERS:
        return True
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_value(key: str, value: Any) -> Any:
    """Return ``[REDACTED]`` for values whose key looks sensitive, else the value unchanged."""
    if _is_sensitive_key(key):
        return "[REDACTED]"
    return value


def _redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {k: redact_value(k, v) for k, v in mapping.items()}


def redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: redact sensitive top-level keys and header-like mappings."""
    for key, value in list(event_dict.items()):
        if _is_sensitive_key(key):
            event_dict[key] = "[REDACTED]"
        elif isinstance(value, Mapping):
            event_dict[key] = _redact_mapping(value)
    return event_dict


def safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return only non-sensitive headers, dropping Authorization/Cookie/Set-Cookie/etc."""
    return {k: v for k, v in headers.items() if not _is_sensitive_key(k)}


def configure_logging(settings: Settings) -> None:
    """Configure structlog and the stdlib root logger.

    ``json`` format is used in production; ``console`` is human-readable for local development.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_processor,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.log_format == "json":
        processors = [
            *shared_processors,
            structlog.processors.JSONRenderer(serializer=json.dumps, ensure_ascii=False),
        ]
    else:
        processors = [*shared_processors, structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=level, format="%(message)s")
    logging.getLogger("uvicorn.access").setLevel(level)


def get_logger(name: str = "livephoto") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def bind_request_context(request_id: str, method: str, path: str) -> None:
    """Bind per-request context into structlog contextvars (cleared by request middleware)."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, method=method, path=path)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
