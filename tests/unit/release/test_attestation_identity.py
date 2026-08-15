from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.release.attestation import REQUIRED_CHECK_IDS, validate_attestation


def _document() -> dict[str, object]:
    return {
        "format": "evidence-review/human-attestation",
        "version": 1,
        "assurance_level": "PROCESS_ATTESTATION",
        "reviewer_id": "reviewer-a@example.com",
        "reviewed_at": "2026-08-02T14:00:00+09:00",
        "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
        "release_candidate_hash": "a" * 64,
        "packet_hash": "b" * 64,
        "checks": [
            {
                "check_id": check_id,
                "status": "PASS",
                "evidence": f"evidence/{check_id}",
            }
            for check_id in REQUIRED_CHECK_IDS
        ],
    }


def test_expected_reviewer_id_must_match_exactly(tmp_path: Path) -> None:
    path = tmp_path / "human-attestation.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")

    accepted = validate_attestation(
        path,
        expected_candidate_hash="a" * 64,
        expected_packet_hash="b" * 64,
        expected_reviewer_id="reviewer-a@example.com",
    )
    assert accepted.reviewer_id == "reviewer-a@example.com"

    with pytest.raises(ValueError, match="REVIEWER_ID_MISMATCH"):
        validate_attestation(
            path,
            expected_candidate_hash="a" * 64,
            expected_packet_hash="b" * 64,
            expected_reviewer_id="reviewer-b@example.com",
        )
