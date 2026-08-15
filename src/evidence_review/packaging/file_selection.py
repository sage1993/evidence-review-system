"""Stable source-file selection for deterministic runtime bundles."""
from __future__ import annotations

from pathlib import Path

_EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)
_EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo"})


def is_bundle_source_file(path: Path, source_root: Path) -> bool:
    """Return whether path is a stable source artifact for a bundle."""
    if not path.is_file():
        return False

    relative = path.relative_to(source_root)

    if path.suffix.lower() in _EXCLUDED_SUFFIXES:
        return False

    for part in relative.parts:
        if part in _EXCLUDED_DIRECTORY_NAMES:
            return False
        if part.endswith(".egg-info"):
            return False

    return True


def iter_bundle_source_files(source_root: Path) -> tuple[Path, ...]:
    """Return stable bundle files in deterministic path order."""
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)

    return tuple(
        path
        for path in sorted(source_root.rglob("*"))
        if is_bundle_source_file(path, source_root)
    )
