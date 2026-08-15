from __future__ import annotations

import json
from pathlib import Path

from evidence_review.review_packet.decision_record import (
    load_latest_valid_human_decision,
    write_human_decision,
)


def _write(
    run: Path,
    *,
    reviewed_at: str,
    decision: str = "SATISFIED",
    notes: str = "확인",
    packet_hash: str = "a" * 64,
) -> Path:
    return write_human_decision(
        run,
        reviewer_id="reviewer-01",
        reviewed_at=reviewed_at,
        packet_hash=packet_hash,
        decision=decision,
        notes=notes,
    )


def test_latest_valid_decision_is_selected_by_reviewed_at(tmp_path: Path) -> None:
    run = tmp_path / "RUN-0123456789ABCDEF0123"
    run.mkdir()
    _write(run, reviewed_at="2026-08-13T12:34:56.100000+00:00", notes="first")
    _write(run, reviewed_at="2026-08-13T12:34:56.900000+00:00", notes="latest")

    record = load_latest_valid_human_decision(run, "a" * 64)

    assert record is not None
    assert record.run_id == run.name
    assert record.reviewer_id == "reviewer-01"
    assert record.reviewed_at == "2026-08-13T12:34:56.900000+00:00"
    assert record.decision == "SATISFIED"
    assert record.notes == "latest"
    assert record.path.name.endswith("-reviewer-01.json")


def test_loader_ignores_malformed_wrong_run_and_wrong_packet_records(tmp_path: Path) -> None:
    run = tmp_path / "RUN-0123456789ABCDEF0123"
    run.mkdir()
    valid = _write(run, reviewed_at="2026-08-13T12:34:56.100000+00:00")
    directory = valid.parent

    (directory / "broken.json").write_text("{", encoding="utf-8")
    (directory / "wrong-run.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-WRONG",
                "reviewer_id": "reviewer-02",
                "reviewed_at": "2026-08-14T12:34:56+00:00",
                "packet_hash": "a" * 64,
                "decision": "SATISFIED",
                "notes": "wrong run",
            }
        ),
        encoding="utf-8",
    )
    (directory / "wrong-packet.json").write_text(
        json.dumps(
            {
                "run_id": run.name,
                "reviewer_id": "reviewer-03",
                "reviewed_at": "2026-08-15T12:34:56+00:00",
                "packet_hash": "b" * 64,
                "decision": "SATISFIED",
                "notes": "wrong packet",
            }
        ),
        encoding="utf-8",
    )

    record = load_latest_valid_human_decision(run, "a" * 64)

    assert record is not None
    assert record.path == valid


def test_decision_filename_uses_microsecond_precision(tmp_path: Path) -> None:
    run = tmp_path / "RUN-0123456789ABCDEF0123"
    run.mkdir()

    first = _write(run, reviewed_at="2026-08-13T12:34:56.100000+00:00")
    second = _write(run, reviewed_at="2026-08-13T12:34:56.900000+00:00")

    assert first != second
    assert "123456100000" in first.name
    assert "123456900000" in second.name
