"""Canonical JSON serialization and hashing utilities."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def dumps(value: Any) -> str:
    """Serialize *value* to deterministic canonical JSON text."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def dump_bytes(value: Any) -> bytes:
    """Serialize *value* to canonical UTF-8 JSON bytes."""
    return dumps(value).encode("utf-8")


def sha256_json(value: Any) -> str:
    """Return the lowercase SHA-256 digest of canonical JSON bytes."""
    return hashlib.sha256(dump_bytes(value)).hexdigest()
