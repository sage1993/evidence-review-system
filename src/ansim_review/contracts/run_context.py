"""Immutable deterministic run identifiers and directories."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ansim_review.canonical_json import sha256_json

_RUN_ID_PATTERN = re.compile(r"^RUN-[0-9A-F]{20}$")


def compute_run_id(
    question: str,
    inputs: Mapping[str, Any],
    evidence_hash: str,
    rule_hash: str,
    formula_hash: str,
) -> str:
    """Compute a stable run ID from all deterministic run inputs."""
    digest = sha256_json(
        {
            "evidence_hash": evidence_hash,
            "formula_hash": formula_hash,
            "inputs": dict(inputs),
            "question": question,
            "rule_hash": rule_hash,
        }
    )
    return f"RUN-{digest[:20].upper()}"


def create_run_directory(root: Path, run_id: str) -> Path:
    """Create a new run directory and refuse any overwrite."""
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("invalid run_id")
    root.mkdir(parents=True, exist_ok=True)
    run_directory = root / run_id
    run_directory.mkdir(exist_ok=False)
    return run_directory
