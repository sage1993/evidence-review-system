"""Canonical Python package for the evidence review runtime.

During the compatibility window, submodules are loaded from the existing
implementation tree without copying source files. New entrypoints and imports
should use ``evidence_review``. The old ``ansim_review`` package remains
available only for existing integrations and serialized runtime bundles.
"""

from __future__ import annotations

from pathlib import Path

import ansim_review as _legacy_package

CANONICAL_PACKAGE = "evidence_review"

# Search the canonical package directory first, then the shared implementation
# tree. This allows ``evidence_review.contracts`` and other existing submodules
# to resolve without maintaining two copies of every source file.
__path__ = [
    str(Path(__file__).resolve().parent),
    *(str(path) for path in _legacy_package.__path__),
]
