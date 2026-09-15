from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
SENSITIVE_FIELD_PARTS = (
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
)
SENSITIVE_QUERY_KEYS = {"api_key", "apikey", "key", "token", "access_token", "password", "secret"}


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in SENSITIVE_FIELD_PARTS)


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc:
        return value
    query = []
    changed = False
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            query.append((key, REDACTED))
            changed = True
        else:
            query.append((key, item))
    netloc = parts.netloc
    if "@" in netloc and ":" in netloc.split("@", 1)[0]:
        netloc = REDACTED + "@" + netloc.split("@", 1)[1]
        changed = True
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), parts.fragment)) if changed else value


def redact_text(value: str, *, configured_secrets: tuple[str, ...] = ()) -> str:
    output = value
    for secret in configured_secrets:
        if secret:
            output = output.replace(secret, REDACTED)
    output = re.sub(r"(?i)(authorization:\s*)(bearer|token)?\s*[A-Za-z0-9._~+/=-]{8,}", r"\1" + REDACTED, output)
    output = re.sub(r"(?i)((api[_-]?key|access[_-]?token|password|secret)=)[^&\s]+", r"\1" + REDACTED, output)
    return _redact_url(output)


def redact(value: Any, *, configured_secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            output[text_key] = REDACTED if _is_sensitive_key(text_key) else redact(item, configured_secrets=configured_secrets)
        return output
    if isinstance(value, list):
        return [redact(item, configured_secrets=configured_secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item, configured_secrets=configured_secrets) for item in value)
    if isinstance(value, str):
        return redact_text(value, configured_secrets=configured_secrets)
    return value
