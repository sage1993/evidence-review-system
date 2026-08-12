"""Shared runtime package selection for deterministic bundle builders."""
from __future__ import annotations

from pathlib import Path

RUNTIME_PACKAGE_NAMES: tuple[str, ...] = ("evidence_review", "ansim_review")


def runtime_package_roots(source_root: Path) -> tuple[tuple[str, Path], ...]:
    """Return canonical and legacy runtime packages in stable order."""
    roots = tuple((name, source_root / name) for name in RUNTIME_PACKAGE_NAMES)
    missing = tuple(name for name, path in roots if not path.is_dir())
    if missing:
        raise FileNotFoundError(", ".join(missing))
    return roots