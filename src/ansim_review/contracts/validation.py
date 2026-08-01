"""Strict validation helpers shared by versioned contract decoders."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from math import isfinite
from typing import TypeVar, cast

_T = TypeVar("_T", bound=str)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def expect_mapping(value: object, field: str) -> Mapping[str, object]:
    """Return *value* as a string-keyed mapping or raise ``ValueError``."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings")
    return cast(Mapping[str, object], value)


def expect_sequence(value: object, field: str) -> Sequence[object]:
    """Return *value* as a non-string sequence or raise ``ValueError``."""
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def expect_string(value: object, field: str, *, allow_empty: bool = False) -> str:
    """Decode a string with optional empty-string support."""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    return value


def expect_int(value: object, field: str) -> int:
    """Decode an integer while rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def expect_bool(value: object, field: str) -> bool:
    """Decode a boolean without truthy coercion."""
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def expect_number(value: object, field: str) -> float:
    """Decode one finite numeric value while rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def expect_literal(value: object, field: str, allowed: tuple[_T, ...]) -> _T:
    """Decode one exact string literal from *allowed*."""
    candidate = expect_string(value, field)
    if candidate not in allowed:
        raise ValueError(f"unsupported {field}: {candidate}")
    return candidate


def expect_string_tuple(value: object, field: str) -> tuple[str, ...]:
    """Decode an array of non-empty strings."""
    return tuple(
        expect_string(item, f"{field}[{index}]")
        for index, item in enumerate(expect_sequence(value, field))
    )


def expect_sha256(value: object, field: str) -> str:
    """Decode a lowercase hexadecimal SHA-256 digest."""
    digest = expect_string(value, field)
    if not _SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return digest


def require_fields(payload: Mapping[str, object], required: set[str], field: str) -> None:
    """Reject documents that omit explicit nullable or collection fields."""
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"{field} is missing required fields: {', '.join(missing)}")


def reject_unknown(payload: Mapping[str, object], allowed: set[str], field: str) -> None:
    """Reject keys that are not explicitly part of the contract."""
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")
