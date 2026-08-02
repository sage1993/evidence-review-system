import json
from pathlib import Path

import pytest

from ansim_review.release.attestation import REQUIRED_CHECK_IDS, validate_attestation


def _record(candidate_hash: str, packet_hash: str) -> dict[str, object]:
    return {
        "format": "evidence-review/human-attestation",
        "version": 1,
        "assurance_level": "PROCESS_ATTESTATION",
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-02T14:00:00+09:00",
        "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [
            {
                "check_id": check_id,
                "status": "PASS",
                "evidence": f"evidence/{check_id}",
            }
            for check_id in REQUIRED_CHECK_IDS
        ],
    }


def test_attestation_requires_named_reviewer_and_all_manual_evidence(
    tmp_path: Path,
) -> None:
    candidate_hash = "a" * 64
    packet_hash = "b" * 64
    path = tmp_path / "human-attestation.json"
    path.write_text(
        json.dumps(_record(candidate_hash, packet_hash)),
        encoding="utf-8",
    )
    accepted = validate_attestation(
        path,
        expected_candidate_hash=candidate_hash,
        expected_packet_hash=packet_hash,
    )
    assert accepted.reviewer_id == "reviewer@example.com"
    assert accepted.assurance_level == "PROCESS_ATTESTATION"

    record = _record(candidate_hash, packet_hash)
    checks = record["checks"]
    assert isinstance(checks, list)
    first = checks[0]
    assert isinstance(first, dict)
    first["status"] = "PENDING"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="ATTESTATION_CHECK_NOT_PASSED"):
        validate_attestation(
            path,
            expected_candidate_hash=candidate_hash,
            expected_packet_hash=packet_hash,
        )
