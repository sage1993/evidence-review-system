"""Append-only human decision records separate from machine packets."""
from __future__ import annotations

import json
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
_DECISION_FIELDS = frozenset(
    {"reviewer_id", "reviewed_at", "packet_hash", "decision", "notes"}
)
_DECISION_RECORD_FIELDS = _DECISION_FIELDS | {"run_id"}


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


def _validated_decision(
    *,
    reviewer_id: str,
    reviewed_at: str,
    packet_hash: str,
    decision: str,
    notes: str,
) -> tuple[str, str, str, str, str]:
    if not reviewer_id.strip():
        raise ValueError("reviewer_id is required")
    if not _SHA256.fullmatch(packet_hash):
        raise ValueError("packet_hash must be a lowercase SHA-256 digest")
    if decision not in _ALLOWED:
        raise ValueError(f"unsupported human decision: {decision}")
    if not notes.strip():
        raise ValueError("notes is required")
    canonical_time, _ = _timestamp(reviewed_at)
    return reviewer_id, canonical_time, packet_hash, decision, notes


def write_human_decision(
    run_directory: Path,
    *,
    reviewer_id: str,
    reviewed_at: str,
    packet_hash: str,
    decision: str,
    notes: str,
) -> Path:
    """Exclusively create one immutable human decision JSON record."""
    run_directory = _regular_directory(run_directory, "run_directory")
    reviewer_id, canonical_time, packet_hash, decision, notes = _validated_decision(
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        packet_hash=packet_hash,
        decision=decision,
        notes=notes,
    )
    _, file_time = _timestamp(canonical_time)
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


def has_valid_human_decision(run_directory: Path, packet_hash: str) -> bool:
    """Return whether a valid append-only decision matches the packet hash."""
    try:
        run_directory = _regular_directory(run_directory, "run_directory")
    except ValueError:
        return False
    if not _SHA256.fullmatch(packet_hash):
        return False
    directory = run_directory / "human-decisions"
    try:
        directory = _regular_directory(directory, "human-decisions")
    except ValueError:
        return False
    try:
        candidates = tuple(directory.iterdir())
    except OSError:
        return False
    for candidate in candidates:
        try:
            status = candidate.lstat()
            if (
                stat.S_ISLNK(status.st_mode)
                or not stat.S_ISREG(status.st_mode)
                or getattr(status, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
                or candidate.suffix != ".json"
            ):
                continue
            document = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or set(document) != _DECISION_RECORD_FIELDS:
                continue
            if document["run_id"] != run_directory.name:
                continue
            if not all(isinstance(document[field], str) for field in _DECISION_FIELDS):
                continue
            values = {field: document[field] for field in _DECISION_FIELDS}
            _, _, candidate_hash, _, _ = _validated_decision(**values)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if candidate_hash == packet_hash:
            return True
    return False
