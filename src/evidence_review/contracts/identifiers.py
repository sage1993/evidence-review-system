"""Shared validation for identifiers that may participate in file paths."""

from __future__ import annotations

import re
from pathlib import Path

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")


def validate_identifier(value: object, field: str) -> str:
    """Return one path-safe stable identifier or raise ``ValueError``."""
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(
            f"{field} must contain only ASCII letters, numbers, dot, underscore, or hyphen"
        )
    return value


def validate_version(value: object, field: str) -> str:
    """Return one semantic version string that cannot alter a path."""
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ValueError(f"{field} must be a path-safe semantic version")
    return value


def safe_direct_child(root: Path, filename: str, field: str) -> Path:
    """Resolve *filename* as exactly one direct child of *root*."""
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or ":" in filename
        or filename in {".", ".."}
    ):
        raise ValueError(f"{field} must be a direct child filename")
    resolved_root = root.resolve()
    candidate = (resolved_root / filename).resolve()
    if candidate.parent != resolved_root:
        raise ValueError(f"{field} escapes its allowed directory")
    return candidate
