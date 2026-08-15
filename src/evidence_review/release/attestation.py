"""Strict named-reviewer process attestation for release authorization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.formats import HUMAN_ATTESTATION_FORMAT
from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)

PROCESS_ATTESTATION: Final[Literal["PROCESS_ATTESTATION"]] = "PROCESS_ATTESTATION"
REVIEWED_AND_ACCEPTED_FOR_RELEASE: Final[
    Literal["REVIEWED_AND_ACCEPTED_FOR_RELEASE"]
] = "REVIEWED_AND_ACCEPTED_FOR_RELEASE"

REQUIRED_CHECK_IDS: Final[tuple[str, ...]] = (
    "SOURCE_IDENTITY",
    "CITATION_PAGE_BBOX",
    "TABLE_AND_VISUAL_EVIDENCE",
    "CALCULATION_TRACE",
    "RULE_VERSION_AND_STATUS",
    "TRACK_A_EXPLANATION",
    "TRACK_B_AUDIT",
    "CONFIDENCE_FACTORS",
    "ABSTENTION_BEHAVIOR",
    "HUMAN_DECISION_SEPARATION",
)
_REQUIRED_CHECK_SET = frozenset(REQUIRED_CHECK_IDS)


@dataclass(frozen=True, slots=True)
class AttestationCheck:
    """One required manual review check with an evidence locator."""

    check_id: str
    status: Literal["PASS"]
    evidence: str


@dataclass(frozen=True, slots=True)
class HumanAttestation:
    """A process record bound to one exact release candidate and packet."""

    format: Literal["evidence-review/human-attestation"]
    version: Literal[1]
    assurance_level: Literal["PROCESS_ATTESTATION"]
    reviewer_id: str
    reviewed_at: datetime
    attestation: Literal["REVIEWED_AND_ACCEPTED_FOR_RELEASE"]
    release_candidate_hash: str
    packet_hash: str
    checks: tuple[AttestationCheck, ...]


def _nonblank(value: object, field: str) -> str:
    result = expect_string(value, field)
    if not result.strip():
        raise ValueError(f"{field} must not be blank")
    return result


def _timestamp(value: object) -> datetime:
    text = expect_string(value, "reviewed_at")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError("reviewed_at must be ISO-8601") from error
    if result.utcoffset() is None:
        raise ValueError("reviewed_at must include timezone")
    return result


def _decode_check(value: object, index: int) -> AttestationCheck:
    payload = expect_mapping(value, f"checks[{index}]")
    fields = {"check_id", "status", "evidence"}
    require_fields(payload, fields, f"checks[{index}]")
    reject_unknown(payload, fields, f"checks[{index}]")
    check_id = _nonblank(payload.get("check_id"), f"checks[{index}].check_id")
    if check_id not in _REQUIRED_CHECK_SET:
        raise ValueError(f"UNKNOWN_ATTESTATION_CHECK:{check_id}")
    status_value = expect_string(payload.get("status"), f"checks[{index}].status")
    if status_value != "PASS":
        raise ValueError(f"ATTESTATION_CHECK_NOT_PASSED:{check_id}")
    evidence = _nonblank(payload.get("evidence"), f"checks[{index}].evidence")
    return AttestationCheck(check_id=check_id, status="PASS", evidence=evidence)


def decode_attestation(value: object) -> HumanAttestation:
    """Decode the strict version 1 process-attestation contract."""
    payload = expect_mapping(value, "attestation")
    expect_literal(payload.get("format"), "format", (HUMAN_ATTESTATION_FORMAT,))
    fields = {
        "format",
        "version",
        "assurance_level",
        "reviewer_id",
        "reviewed_at",
        "attestation",
        "release_candidate_hash",
        "packet_hash",
        "checks",
    }
    require_fields(payload, fields, "attestation")
    reject_unknown(payload, fields, "attestation")
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    assurance = expect_literal(
        payload.get("assurance_level"),
        "assurance_level",
        (PROCESS_ATTESTATION,),
    )
    statement = expect_literal(
        payload.get("attestation"),
        "attestation",
        (REVIEWED_AND_ACCEPTED_FOR_RELEASE,),
    )

    by_id: dict[str, AttestationCheck] = {}
    for index, item in enumerate(expect_sequence(payload.get("checks"), "checks")):
        check = _decode_check(item, index)
        if check.check_id in by_id:
            raise ValueError(f"DUPLICATE_ATTESTATION_CHECK:{check.check_id}")
        by_id[check.check_id] = check
    missing = [check_id for check_id in REQUIRED_CHECK_IDS if check_id not in by_id]
    if missing:
        raise ValueError(f"MISSING_ATTESTATION_CHECK:{missing[0]}")
    ordered = tuple(by_id[check_id] for check_id in REQUIRED_CHECK_IDS)

    return HumanAttestation(
        format=HUMAN_ATTESTATION_FORMAT,
        version=1,
        assurance_level=assurance,
        reviewer_id=_nonblank(payload.get("reviewer_id"), "reviewer_id"),
        reviewed_at=_timestamp(payload.get("reviewed_at")),
        attestation=statement,
        release_candidate_hash=expect_sha256(
            payload.get("release_candidate_hash"),
            "release_candidate_hash",
        ),
        packet_hash=expect_sha256(payload.get("packet_hash"), "packet_hash"),
        checks=ordered,
    )


def validate_attestation(
    path: Path,
    *,
    expected_candidate_hash: str,
    expected_packet_hash: str,
    expected_reviewer_id: str | None = None,
) -> HumanAttestation:
    """Validate a record and bind it to exact artifacts and reviewer policy."""
    expected_candidate = expect_sha256(
        expected_candidate_hash,
        "expected_candidate_hash",
    )
    expected_packet = expect_sha256(expected_packet_hash, "expected_packet_hash")
    reviewer_id = (
        None
        if expected_reviewer_id is None
        else _nonblank(expected_reviewer_id, "expected_reviewer_id")
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    attestation = decode_attestation(payload)
    if reviewer_id is not None and attestation.reviewer_id != reviewer_id:
        raise ValueError("REVIEWER_ID_MISMATCH")
    if attestation.release_candidate_hash != expected_candidate:
        raise ValueError("RELEASE_CANDIDATE_HASH_MISMATCH")
    if attestation.packet_hash != expected_packet:
        raise ValueError("PACKET_HASH_MISMATCH")
    return attestation


def attestation_document(attestation: HumanAttestation) -> dict[str, object]:
    """Return the canonical JSON document for a validated attestation."""
    checks = {check.check_id: check for check in attestation.checks}
    return {
        "format": HUMAN_ATTESTATION_FORMAT,
        "version": 1,
        "assurance_level": PROCESS_ATTESTATION,
        "reviewer_id": attestation.reviewer_id,
        "reviewed_at": attestation.reviewed_at.isoformat(),
        "attestation": REVIEWED_AND_ACCEPTED_FOR_RELEASE,
        "release_candidate_hash": attestation.release_candidate_hash,
        "packet_hash": attestation.packet_hash,
        "checks": [
            {
                "check_id": check_id,
                "status": checks[check_id].status,
                "evidence": checks[check_id].evidence,
            }
            for check_id in REQUIRED_CHECK_IDS
        ],
    }


def write_attestation(path: Path, attestation: HumanAttestation) -> str:
    """Write canonical bytes with exclusive creation and return their SHA-256."""
    content = dump_bytes(attestation_document(attestation))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
    return hashlib.sha256(content).hexdigest()
