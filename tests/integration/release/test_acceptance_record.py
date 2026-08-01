import json
from pathlib import Path

import pytest

from ansim_review.release.acceptance import validate_acceptance_record


def _record(candidate_hash: str, packet_hash: str) -> dict[str, object]:
    check_ids = (
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
    return {
        "format": "ansim/human-acceptance",
        "version": 1,
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-01T16:00:00+09:00",
        "signature": "reviewer@example.com:approved",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [
            {
                "check_id": check_id,
                "status": "PASS",
                "evidence": f"evidence/{check_id}",
            }
            for check_id in check_ids
        ],
    }


def test_acceptance_requires_named_reviewer_and_all_manual_evidence(
    tmp_path: Path,
) -> None:
    candidate_hash = "a" * 64
    packet_hash = "b" * 64
    path = tmp_path / "acceptance-record.json"
    path.write_text(
        json.dumps(_record(candidate_hash, packet_hash)),
        encoding="utf-8",
    )
    accepted = validate_acceptance_record(
        path,
        expected_candidate_hash=candidate_hash,
        expected_packet_hash=packet_hash,
    )
    assert accepted["reviewer_id"] == "reviewer@example.com"
    record = _record(candidate_hash, packet_hash)
    checks = record["checks"]
    assert isinstance(checks, list)
    first = checks[0]
    assert isinstance(first, dict)
    first["status"] = "PENDING"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="did not pass"):
        validate_acceptance_record(
            path,
            expected_candidate_hash=candidate_hash,
            expected_packet_hash=packet_hash,
        )
