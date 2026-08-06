"""Append-only human decision records separate from machine packets."""
from __future__ import annotations

import re
import stat
from datetime import datetime
from pathlib import Path

from ansim_review.canonical_json import dump_bytes

_ALLOWED = {
    "SATISFIED",
    "NOT_SATISFIED",
    "CONDITIONAL",
    "ADDITIONAL_REVIEW_REQUIRED",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_REPARSE_POINT_ATTRIBUTE = 0x400


def _timestamp(value: str) -> tuple[str, str]:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("reviewed_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("reviewed_at must include a timezone")
    return parsed.isoformat(), parsed.strftime("%Y%m%dT%H%M%S%z")


def _regular_directory(path: Path, field: str) -> Path:
    try:
        status = path.lstat()
    except OSError as error:
        raise ValueError(f"{field} must be an existing regular directory") from error
    if (
        stat.S_ISLNK(status.st_mode)
        or not stat.S_ISDIR(status.st_mode)
        or getattr(status, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    ):
        raise ValueError(f"{field} must be an existing regular directory")
    return path.resolve(strict=True)


def write_human_decision(
    run_directory: Path,
    *,
    reviewer_id: str,
    reviewed_at: str,
    packet_hash: str,
    decision: str,
    notes: str = "",
) -> Path:
    """Exclusively create one immutable human decision JSON record."""
    run_directory = _regular_directory(run_directory, "run_directory")
    if not reviewer_id.strip():
        raise ValueError("reviewer_id is required")
    if not _SHA256.fullmatch(packet_hash):
        raise ValueError("packet_hash must be a lowercase SHA-256 digest")
    if decision not in _ALLOWED:
        raise ValueError(f"unsupported human decision: {decision}")
    canonical_time, file_time = _timestamp(reviewed_at)
    safe_reviewer = _SAFE.sub("-", reviewer_id.strip()).strip("-")
    if not safe_reviewer:
        raise ValueError("reviewer_id has no safe filename characters")
    directory = run_directory / "human-decisions"
    directory.mkdir(parents=True, exist_ok=True)
    directory = _regular_directory(directory, "human-decisions")
    output = directory / f"{file_time}-{safe_reviewer}.json"
    payload = {
        "run_id": run_directory.name,
        "reviewer_id": reviewer_id,
        "reviewed_at": canonical_time,
        "packet_hash": packet_hash,
        "decision": decision,
        "notes": notes,
    }
    with output.open("xb") as stream:
        stream.write(dump_bytes(payload))
    return output
