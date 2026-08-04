"""Version-bound run identity for resumable review orchestration."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ansim_review.canonical_json import dump_bytes, sha256_json
from ansim_review.contracts.validation import expect_string
from ansim_review.workflow.orchestrator import prepare_review_run
from ansim_review.workflow.request import ReviewRequest, review_request_sha256
from ansim_review.workflow.run_layout import ReviewRunLayout


def _version(value: str, field: str) -> str:
    return expect_string(value, field)


def _version_binding(
    request: ReviewRequest,
    *,
    evidence_version: str,
    rule_version: str,
    formula_version: str,
) -> dict[str, str]:
    return {
        "request_sha256": review_request_sha256(request),
        "evidence_version": _version(evidence_version, "evidence_version"),
        "rule_version": _version(rule_version, "rule_version"),
        "formula_version": _version(formula_version, "formula_version"),
    }


def compute_versioned_run_id(
    request: ReviewRequest,
    *,
    evidence_version: str,
    rule_version: str,
    formula_version: str,
) -> str:
    """Derive a new immutable run ID whenever any deterministic input changes."""
    binding = _version_binding(
        request,
        evidence_version=evidence_version,
        rule_version=rule_version,
        formula_version=formula_version,
    )
    return f"RUN-{sha256_json(binding)[:20].upper()}"


def _persist_binding(layout: ReviewRunLayout, binding: dict[str, str]) -> Path:
    path = layout.machine_dir / "version-binding.json"
    payload = dump_bytes(
        {
            "format": "evidence-review/version-binding",
            "version": 1,
            "run_id": layout.run_id,
            **binding,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError("existing version binding differs") from None
        return path
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def prepare_versioned_review_run(
    runs_root: Path,
    request: ReviewRequest,
    *,
    evidence_version: str,
    rule_version: str,
    formula_version: str,
    recorded_at: str,
) -> ReviewRunLayout:
    """Prepare or resume the run identified by request and engine versions."""
    binding = _version_binding(
        request,
        evidence_version=evidence_version,
        rule_version=rule_version,
        formula_version=formula_version,
    )
    run_id = compute_versioned_run_id(
        request,
        evidence_version=evidence_version,
        rule_version=rule_version,
        formula_version=formula_version,
    )
    layout = prepare_review_run(
        runs_root,
        run_id,
        request,
        recorded_at=recorded_at,
    )
    _persist_binding(layout, binding)
    return layout


__all__ = [
    "compute_versioned_run_id",
    "prepare_versioned_review_run",
]
