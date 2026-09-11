"""Shared runtime package selection for deterministic bundle builders."""
from __future__ import annotations

from pathlib import Path

from evidence_review.packaging.file_selection import missing_bundle_source_files

RUNTIME_PACKAGE_NAMES: tuple[str, ...] = ("evidence_review", "ansim_review")
REVIEW_MATTER_RUNTIME_PATHS: tuple[str, ...] = (
    "evidence_review/review_matter/schema.sql",
    "evidence_review/workbench/assets/workbench.css",
    "evidence_review/workbench/assets/workbench.js",
)


def missing_runtime_package_files(source_root: Path) -> tuple[str, ...]:
    """Return required ReviewMatter runtime files absent from source selection."""
    return missing_bundle_source_files(source_root, REVIEW_MATTER_RUNTIME_PATHS)


def runtime_package_roots(source_root: Path) -> tuple[tuple[str, Path], ...]:
    """Return canonical and legacy runtime packages in stable order."""
    roots = tuple((name, source_root / name) for name in RUNTIME_PACKAGE_NAMES)
    missing = tuple(name for name, path in roots if not path.is_dir())
    if missing:
        raise FileNotFoundError(", ".join(missing))
    runtime_missing = missing_runtime_package_files(source_root)
    if runtime_missing:
        raise FileNotFoundError(", ".join(runtime_missing))
    return roots
