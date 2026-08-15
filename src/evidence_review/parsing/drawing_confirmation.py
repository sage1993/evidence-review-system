"""Append-only reviewer confirmations for drawing candidates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from evidence_review.contracts.drawing import (
    CandidateStatus,
    DrawingCandidate,
    DrawingConfirmation,
    decode_drawing_confirmation,
    geometry_document,
)
from evidence_review.parsing.drawing_case import (
    CaseManifestEntry,
    case_artifact_path,
    validate_artifact_id,
    write_canonical_create_only,
)


def drawing_confirmation_document(
    confirmation: DrawingConfirmation,
) -> dict[str, object]:
    """Return the explicit canonical document for one confirmation."""
    return {
        "confirmation_id": confirmation.confirmation_id,
        "candidate_id": confirmation.candidate_id,
        "action": confirmation.action,
        "source_sha256": confirmation.source_sha256,
        "reviewer": confirmation.reviewer,
        "confirmed_at": confirmation.confirmed_at,
        "confirmed_value": confirmation.confirmed_value,
        "unit": confirmation.unit,
        "geometry": (
            None
            if confirmation.geometry is None
            else geometry_document(confirmation.geometry)
        ),
    }


def parse_confirmation_time(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and require an explicit UTC offset."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("confirmed_at must be an ISO-8601 datetime") from error
    if parsed.utcoffset() is None:
        raise ValueError("confirmed_at must include an explicit UTC offset")
    return parsed


def _validated_confirmation(
    confirmation: DrawingConfirmation,
) -> DrawingConfirmation:
    return decode_drawing_confirmation(drawing_confirmation_document(confirmation))


def validate_confirmation_for_candidate(
    candidate: DrawingCandidate,
    confirmation: DrawingConfirmation,
) -> CandidateStatus:
    """Validate one reviewer action and return its effective candidate status."""
    validated = _validated_confirmation(confirmation)
    if validated.candidate_id != candidate.candidate_id:
        raise ValueError("confirmation candidate_id does not match candidate")
    if validated.source_sha256 != candidate.source_sha256:
        raise ValueError("confirmation source_sha256 does not match candidate")
    parse_confirmation_time(validated.confirmed_at)

    if validated.geometry is not None:
        if validated.geometry.coordinate_system != candidate.geometry.coordinate_system:
            raise ValueError("replacement geometry must keep the candidate coordinate system")

    if validated.confirmed_value is not None and not validated.unit:
        raise ValueError("unit is required when confirmed_value is present")
    if validated.unit is not None and validated.confirmed_value is None:
        raise ValueError("confirmed_value is required when unit is present")

    if validated.action == "REJECTED":
        if (
            validated.confirmed_value is not None
            or validated.unit is not None
            or validated.geometry is not None
        ):
            raise ValueError("REJECTED confirmation cannot contain confirmed data")
        return "REJECTED"

    if candidate.status in ("REJECTED", "CONFLICT"):
        raise ValueError(f"candidate status cannot be confirmed: {candidate.status}")

    if validated.action == "ACCEPTED":
        if (
            validated.confirmed_value is not None
            or validated.unit is not None
            or validated.geometry is not None
        ):
            raise ValueError("ACCEPTED confirmation cannot replace candidate data")
        return "ACCEPTED"

    if validated.action == "EDITED":
        if validated.confirmed_value is None and validated.geometry is None:
            raise ValueError("EDITED confirmation requires confirmed value or geometry")
        return "EDITED"

    if validated.action == "CREATED":
        if candidate.origin != "REVIEWER_MANUAL" or candidate.status != "CREATED":
            raise ValueError("CREATED confirmation requires a reviewer-manual CREATED candidate")
        if validated.confirmed_value is None and validated.geometry is None:
            raise ValueError("CREATED confirmation requires confirmed value or geometry")
        return "CREATED"

    raise ValueError(f"unsupported confirmation action: {validated.action}")


def persist_confirmation(
    case_dir: Path,
    reviewer_token: str,
    candidate: DrawingCandidate,
    confirmation: DrawingConfirmation,
) -> CaseManifestEntry:
    """Persist one confirmation with create-only append semantics."""
    validate_artifact_id(reviewer_token, "reviewer_token")
    validate_artifact_id(confirmation.confirmation_id, "confirmation_id")
    validated = _validated_confirmation(confirmation)
    validate_confirmation_for_candidate(candidate, validated)
    timestamp = parse_confirmation_time(validated.confirmed_at)
    utc_token = timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{utc_token}-{reviewer_token}-{validated.confirmation_id}.json"
    relative_path = f"confirmations/{filename}"
    path = case_artifact_path(case_dir, relative_path)
    digest = write_canonical_create_only(
        path,
        drawing_confirmation_document(validated),
    )
    return CaseManifestEntry(
        artifact_id=validated.confirmation_id,
        relative_path=relative_path,
        sha256=digest,
    )


def load_and_verify_confirmation(
    case_dir: Path,
    entry: CaseManifestEntry,
) -> DrawingConfirmation:
    """Load one confirmation after verifying its canonical file hash."""
    path = case_artifact_path(case_dir, entry.relative_path)
    payload_bytes = path.read_bytes()
    actual_hash = hashlib.sha256(payload_bytes).hexdigest()
    if actual_hash != entry.sha256:
        raise ValueError("confirmation hash mismatch")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("confirmation document is invalid JSON") from error
    confirmation = decode_drawing_confirmation(payload)
    if confirmation.confirmation_id != entry.artifact_id:
        raise ValueError("confirmation file identity mismatch")
    return confirmation
