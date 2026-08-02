"""Create immutable approved copies without granting runtime authority."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from ansim_review.contracts.identifiers import safe_direct_child
from ansim_review.rule_engine.loader import load_rule


def _validate_review(reviewer_id: str, review_date: str) -> None:
    if not reviewer_id.strip():
        raise ValueError("reviewer identity is required")
    if not review_date.strip():
        raise ValueError("review date is required")
    try:
        date.fromisoformat(review_date)
    except ValueError as error:
        raise ValueError("review date must use ISO YYYY-MM-DD") from error


def _same_inode(path: Path, device: int, inode: int) -> bool:
    try:
        status = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    return not path.is_symlink() and status.st_dev == device and status.st_ino == inode


def approve_candidate(
    candidate_path: Path,
    approved_dir: Path,
    *,
    reviewer_id: str,
    review_date: str,
) -> Path:
    """Create one byte-identical approved copy without editing active authority."""
    _validate_review(reviewer_id, review_date)
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise ValueError("candidate rule does not exist or is not a regular file")
    candidate_bytes = candidate_path.read_bytes()
    try:
        payload = json.loads(candidate_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("candidate rule must be UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("candidate rule must be an object")
    rule = load_rule(payload)
    approved_path = safe_direct_child(
        approved_dir,
        f"{rule.rule_id}@{rule.version}.json",
        "approved_rule_path",
    )
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(approved_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    created = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(candidate_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if _same_inode(approved_path, created.st_dev, created.st_ino):
            approved_path.unlink(missing_ok=True)
        raise
    return approved_path


def promote_candidate(
    candidate_path: Path,
    approved_dir: Path,
    manifest_path: Path,
    *,
    reviewer_id: str,
    review_date: str,
) -> Path:
    """Reject the removed direct active-manifest mutation workflow."""
    del candidate_path, approved_dir, manifest_path, reviewer_id, review_date
    raise ValueError("direct active promotion is disabled")
