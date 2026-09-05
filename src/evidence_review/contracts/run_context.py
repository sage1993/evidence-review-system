"""Immutable deterministic run identifiers and directories."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evidence_review.canonical_json import sha256_json
from evidence_review.filesystem_trust import verified_regular_directory

_RUN_ID_PATTERN = re.compile(r"^RUN-[0-9A-F]{20}$")


def _run_id(document: Mapping[str, Any]) -> str:
    digest = sha256_json(dict(document))
    return f"RUN-{digest[:20].upper()}"


def compute_run_id_from_request(request_document: Mapping[str, Any]) -> str:
    """Compute a stable ID from the complete normalized deterministic request."""
    return _run_id(request_document)


def compute_run_id(
    question: str,
    inputs: Mapping[str, Any],
    evidence_hash: str,
    rule_hash: str,
    formula_hash: str,
) -> str:
    """Compute a legacy run ID from the original fragmented input contract."""
    return _run_id(
        {
            "evidence_hash": evidence_hash,
            "formula_hash": formula_hash,
            "inputs": dict(inputs),
            "question": question,
            "rule_hash": rule_hash,
        }
    )


def create_run_directory(root: Path, run_id: str) -> Path:
    """Create a new run directory below a verified regular runs root."""
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("invalid run_id")
    root.mkdir(parents=True, exist_ok=True)
    verified_root = verified_regular_directory(root, field="runs root")
    run_directory = verified_root / run_id
    run_directory.mkdir(exist_ok=False)
    return verified_regular_directory(run_directory, field="run directory")
