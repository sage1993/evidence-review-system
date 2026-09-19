from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence_review.release.report_as_of import build_report_as_of
from evidence_review.review_packet.decision_record import write_human_decision


def test_report_projection_is_bound_to_packet_and_cutoff(tmp_path: Path) -> None:
    run = tmp_path / "RUN-0123456789ABCDEF0123"
    run.mkdir()
    packet = {"run_id": run.name, "status": "READY_FOR_HUMAN_REVIEW"}
    packet_path = run / "final-review-packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    packet_hash = hashlib.sha256(packet_path.read_bytes()).hexdigest()

    write_human_decision(
        run,
        reviewer_id="reviewer-before",
        reviewed_at="2026-09-17T10:00:00+00:00",
        packet_hash=packet_hash,
        decision="CONDITIONAL",
        notes="before cutoff",
    )
    write_human_decision(
        run,
        reviewer_id="reviewer-after",
        reviewed_at="2026-09-17T12:00:00+00:00",
        packet_hash=packet_hash,
        decision="SATISFIED",
        notes="after cutoff",
    )

    projection = build_report_as_of(
        run,
        as_of="2026-09-17T11:00:00+00:00",
        expected_packet_sha256=packet_hash,
    )

    assert projection["packet_sha256"] == packet_hash
    assert projection["machine_status"] == "READY_FOR_HUMAN_REVIEW"
    assert projection["as_of"] == "2026-09-17T11:00:00+00:00"
    assert projection["human_decision"] == {
        "reviewer_id": "reviewer-before",
        "reviewed_at": "2026-09-17T10:00:00+00:00",
        "packet_sha256": packet_hash,
        "decision": "CONDITIONAL",
        "notes": "before cutoff",
    }
    assert len(tuple((run / "human-decisions").iterdir())) == 2


def test_report_projection_rejects_packet_hash_change(tmp_path: Path) -> None:
    run = tmp_path / "RUN-0123456789ABCDEF0123"
    run.mkdir()
    (run / "final-review-packet.json").write_text(
        json.dumps({"run_id": run.name, "status": "ABSTAIN"}),
        encoding="utf-8",
    )

    try:
        build_report_as_of(
            run,
            as_of="2026-09-17T11:00:00+00:00",
            expected_packet_sha256="a" * 64,
        )
    except ValueError as error:
        assert "hash" in str(error)
    else:
        raise AssertionError("packet hash mismatch must fail closed")
