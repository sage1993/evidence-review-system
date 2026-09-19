"""Fail-closed sanitization for reports leaving the local review boundary."""
from __future__ import annotations

import re
from collections.abc import Mapping

from evidence_review.canonical_json import dump_bytes

type PublicValue = (
    None
    | bool
    | int
    | float
    | str
    | list[PublicValue]
    | dict[str, PublicValue]
)

_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(access[_-]?token|refresh[_-]?token|authorization|api[_-]?key|"
    r"session(?:[_-]?id|[_-]?token)?|cookie|csrf|secret|password|private[_-]?key|nonce)(?:$|[_-])",
    re.IGNORECASE,
)
_SENSITIVE_ARTIFACT_KEY = re.compile(
    r"^(?:drawing|subject[_-]?assets?|workspace[_-](?:id|root|data|path)|"
    r"reference[_-]?workspace|attachment(?:s)?|page[_-]?images?|"
    r"evidence[_-]?db|raw[_-]?image|case[_-]?visual(?:[_-].*)?)$",
    re.IGNORECASE,
)
_TOKEN_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:access[_-]?token|refresh[_-]?token|authorization|api[_-]?key|"
    r"session[_-]?(?:id|token)?|csrf|secret|password)\s*[=:]\s*)([^\s,;&]+)"
)
_LOOPBACK_URL = re.compile(
    r"(?i)\b(?:https?|wss?)://(?:localhost|127\.0\.0\.1|\[?::1\]?)(?::\d+)?[^\s<>\"']*"
)
_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\)[^\r\n<>\"']+")
_POSIX_PATH = re.compile(
    r"(?<![A-Za-z0-9])/(?:Users|home|tmp|var/tmp|private/tmp|workspace)/[^\r\n\s<>\"']+",
    re.IGNORECASE,
)


class PublicSanitizationError(ValueError):
    """Raised when a value cannot be represented as a safe public document."""


def _sensitive_key(key: str) -> bool:
    normalized = key.replace(" ", "_")
    return bool(_SENSITIVE_KEY.search(normalized))


def _sanitize_text(value: str) -> str:
    value = _TOKEN_ASSIGNMENT.sub(r"\1<redacted:secret>", value)
    value = _LOOPBACK_URL.sub("<redacted:loopback-url>", value)
    value = _WINDOWS_PATH.sub("<redacted:local-path>", value)
    value = _POSIX_PATH.sub("<redacted:local-path>", value)
    return value


def _sanitize(value: object, *, key: str | None = None) -> PublicValue:
    if key is not None and _SENSITIVE_ARTIFACT_KEY.fullmatch(key):
        return "<redacted:sensitive-artifact>"
    if key is not None and _sensitive_key(key):
        return "<redacted:secret>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, Mapping):
        result: dict[str, PublicValue] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise PublicSanitizationError("public document keys must be strings")
            result[raw_key] = _sanitize(raw_value, key=raw_key)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    raise PublicSanitizationError(
        f"unsupported public document value: {type(value).__name__}"
    )


def sanitize_public_document(value: object) -> PublicValue:
    """Return a JSON-shaped copy with local and session-bound values redacted."""
    return _sanitize(value)


def sanitize_public_json(value: object) -> bytes:
    """Serialize a sanitized public document with canonical JSON bytes."""
    return dump_bytes(sanitize_public_document(value))


__all__ = [
    "PublicSanitizationError",
    "sanitize_public_document",
    "sanitize_public_json",
]
