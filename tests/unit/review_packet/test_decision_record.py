import json
from pathlib import Path

import pytest

from ansim_review.review_packet.decision_record import write_human_decision


def test_decision_record_requires_identity_hash_allowed_value_and_is_append_only(
    tmp_path: Path,
) -> None:
    run = tmp_path / "RUN-0123456789ABCDEF0123"
    run.mkdir()
    path = write_human_decision(
        run,
        reviewer_id="kim.sh",
        reviewed_at="2026-08-01T15:30:00+09:00",
        packet_hash="a" * 64,
        decision="ADDITIONAL_REVIEW_REQUIRED",
        notes="bbox 재확인",
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.parent.name == "human-decisions"
    assert data["reviewer_id"] == "kim.sh"
    assert data["packet_hash"] == "a" * 64
    assert data["decision"] == "ADDITIONAL_REVIEW_REQUIRED"
    with pytest.raises(FileExistsError):
        write_human_decision(
            run,
            reviewer_id="kim.sh",
            reviewed_at="2026-08-01T15:30:00+09:00",
            packet_hash="a" * 64,
            decision="ADDITIONAL_REVIEW_REQUIRED",
        )
    with pytest.raises(ValueError, match="unsupported human decision"):
        write_human_decision(
            run,
            reviewer_id="kim.sh",
            reviewed_at="2026-08-01T15:31:00+09:00",
            packet_hash="a" * 64,
            decision="PASS",
        )
    with pytest.raises(ValueError, match="packet_hash"):
        write_human_decision(
            run,
            reviewer_id="kim.sh",
            reviewed_at="2026-08-01T15:32:00+09:00",
            packet_hash="bad",
            decision="SATISFIED",
        )
