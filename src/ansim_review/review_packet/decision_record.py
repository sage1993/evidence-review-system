"""Append-only human decision records separate from machine packets."""
from __future__ import annotations

import json
import re
import stat
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.identifiers import validate_identifier

_ALLOWED = {
    "SATISFIED",
    "NOT_SATISFIED",
    "CONDITIONAL",
    "ADDITIONAL_REVIEW_REQUIRED",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_REPARSE_POINT_ATTRIBUTE = 0x400
_REQUEST_FIELDS = frozenset({"reviewer_id", "packet_hash", "decision", "notes"})
_ENVELOPE_FIELDS = _REQUEST_FIELDS | {"reviewed_at"}
_DECISION_RECORD_FIELDS = _ENVELOPE_FIELDS | {"run_id"}


def _timestamp(value: str) -> tuple[str, str]:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("reviewed_at must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone")
    canonical = parsed.isoformat()
    return canonical, parsed.strftime("%Y%m%dT%H%M%S%z")


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


def validate_human_decision_request(value: object) -> dict[str, str]:
    """Validate request-v2: reviewer identity, packet binding, decision and notes only."""
    if not isinstance(value, Mapping) or set(value) != _REQUEST_FIELDS:
        raise ValueError("invalid human decision request")
    if not all(isinstance(value[field], str) for field in _REQUEST_FIELDS):
        raise ValueError("invalid human decision request")
    reviewer_id = validate_identifier(cast(str, value["reviewer_id"]), "reviewer_id")
    packet_hash = cast(str, value["packet_hash"])
    decision = cast(str, value["decision"])
    notes = cast(str, value["notes"])
    if not _SHA256.fullmatch(packet_hash):
        raise ValueError("packet_hash must be a lowercase SHA-256 digest")
    if decision not in _ALLOWED:
        raise ValueError(f"unsupported human decision: {decision}")
    if not notes.strip():
        raise ValueError("notes is required")
    return {
        "reviewer_id": reviewer_id,
        "packet_hash": packet_hash,
        "decision": decision,
        "notes": notes,
    }


def validate_human_decision_envelope(value: object) -> dict[str, str]:
    """Validate the archival five-field decision envelope."""
    if not isinstance(value, Mapping) or set(value) != _ENVELOPE_FIELDS:
        raise ValueError("invalid human decision envelope")
    request = validate_human_decision_request(
        {field: value[field] for field in _REQUEST_FIELDS}
    )
    reviewed_at = value.get("reviewed_at")
    if not isinstance(reviewed_at, str):
        raise ValueError("reviewed_at must be a string")
    canonical_time, _ = _timestamp(reviewed_at)
    return {**request, "reviewed_at": canonical_time}


def build_human_decision_envelope(
    request: object,
    *,
    reviewed_at: datetime | None = None,
) -> dict[str, str]:
    """Bind a validated request to a server-controlled offset-aware timestamp."""
    validated = validate_human_decision_request(request)
    timestamp = reviewed_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone")
    return validate_human_decision_envelope(
        {**validated, "reviewed_at": timestamp.isoformat()}
    )


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
    envelope = validate_human_decision_envelope(
        {
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at,
            "packet_hash": packet_hash,
            "decision": decision,
            "notes": notes,
        }
    )
    _, file_time = _timestamp(envelope["reviewed_at"])
    safe_reviewer = _SAFE.sub("-", envelope["reviewer_id"].strip()).strip("-")
    if not safe_reviewer:
        raise ValueError("reviewer_id has no safe filename characters")
    directory = run_directory / "human-decisions"
    directory.mkdir(parents=True, exist_ok=True)
    directory = _regular_directory(directory, "human-decisions")
    output = directory / f"{file_time}-{safe_reviewer}.json"
    payload = {"run_id": run_directory.name, **envelope}
    with output.open("xb") as stream:
        stream.write(dump_bytes(payload))
    return output


def import_human_decision_envelope(
    run_directory: Path,
    envelope: object,
    *,
    expected_packet_hash: str,
) -> Path:
    """Approved archival import path; reject stale/tampered packet bindings."""
    validated = validate_human_decision_envelope(envelope)
    if validated["packet_hash"] != expected_packet_hash:
        raise ValueError("packet_hash does not match the immutable packet")
    return write_human_decision(run_directory, **validated)


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
            envelope = {field: document[field] for field in _ENVELOPE_FIELDS}
            validated = validate_human_decision_envelope(envelope)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if validated["packet_hash"] == packet_hash:
            return True
    return False


__all__ = [
    "build_human_decision_envelope",
    "has_valid_human_decision",
    "import_human_decision_envelope",
    "validate_human_decision_envelope",
    "validate_human_decision_request",
    "write_human_decision",
]
