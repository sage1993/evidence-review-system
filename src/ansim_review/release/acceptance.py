"""Validate legacy named-reviewer acceptance records.

This module remains for release compatibility until the separate process-
attestation hardening issue is completed. It is not a new artifact writer.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from ansim_review.contracts.legacy_formats import LEGACY_HUMAN_ACCEPTANCE_FORMAT

_SHA = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_CHECKS = (
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


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


def validate_acceptance_record(
    path: Path,
    *,
    expected_candidate_hash: str,
    expected_packet_hash: str,
) -> dict[str, object]:
    """Require reviewer identity, evidence links, and exact release hashes."""
    payload = _mapping(
        json.loads(path.read_text(encoding="utf-8")),
        "acceptance",
    )
    if payload.get("format") != LEGACY_HUMAN_ACCEPTANCE_FORMAT or payload.get(
        "version"
    ) != 1:
        raise ValueError("unsupported acceptance format")
    reviewer = _string(payload.get("reviewer_id"), "reviewer_id")
    signature = _string(payload.get("signature"), "signature")
    reviewed_at = _string(payload.get("reviewed_at"), "reviewed_at")
    try:
        parsed = datetime.fromisoformat(reviewed_at)
    except ValueError as error:
        raise ValueError("reviewed_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("reviewed_at must include timezone")
    candidate_hash = _string(
        payload.get("release_candidate_hash"),
        "release_candidate_hash",
    )
    packet_hash = _string(payload.get("packet_hash"), "packet_hash")
    if not _SHA.fullmatch(candidate_hash) or candidate_hash != expected_candidate_hash:
        raise ValueError("release candidate hash mismatch")
    if not _SHA.fullmatch(packet_hash) or packet_hash != expected_packet_hash:
        raise ValueError("packet hash mismatch")
    checks: dict[str, Mapping[str, object]] = {}
    for index, item in enumerate(_sequence(payload.get("checks"), "checks")):
        check = _mapping(item, f"checks[{index}]")
        check_id = _string(check.get("check_id"), "check_id")
        if check_id in checks:
            raise ValueError(f"duplicate acceptance check: {check_id}")
        checks[check_id] = check
    missing = [check_id for check_id in _REQUIRED_CHECKS if check_id not in checks]
    if missing:
        raise ValueError(f"missing acceptance checks: {', '.join(missing)}")
    for check_id in _REQUIRED_CHECKS:
        check = checks[check_id]
        if check.get("status") != "PASS":
            raise ValueError(f"acceptance check did not pass: {check_id}")
        _string(check.get("evidence"), f"{check_id}.evidence")
    return {
        "reviewer_id": reviewer,
        "reviewed_at": parsed.isoformat(),
        "signature": signature,
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": list(_REQUIRED_CHECKS),
    }
