from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ansim_review.review_packet.decision_record import (
    build_human_decision_envelope,
    import_human_decision_envelope,
    validate_human_decision_envelope,
    validate_human_decision_request,
)


def _request() -> dict[str, str]:
    return {
        "reviewer_id": "reviewer-01",
        "packet_hash": "a" * 64,
        "decision": "SATISFIED",
        "notes": "근거 확인 완료",
    }


def test_request_v2_excludes_reviewed_at_and_envelope_adds_offset_time() -> None:
    request = validate_human_decision_request(_request())

    envelope = build_human_decision_envelope(
        request,
        reviewed_at=datetime(2026, 8, 13, 12, 34, 56, tzinfo=UTC),
    )

    assert set(request) == {"reviewer_id", "packet_hash", "decision", "notes"}
    assert set(envelope) == {
        "reviewer_id",
        "reviewed_at",
        "packet_hash",
        "decision",
        "notes",
    }
    assert envelope["reviewed_at"] == "2026-08-13T12:34:56+00:00"


def test_envelope_rejects_naive_or_clock_only_time() -> None:
    for reviewed_at in ("2026-08-13T12:34:56", "1:03"):
        with pytest.raises(ValueError):
            validate_human_decision_envelope({**_request(), "reviewed_at": reviewed_at})


def test_approved_import_binds_packet_hash_and_is_create_only(tmp_path: Path) -> None:
    run = tmp_path / "RUN-0123456789ABCDEF0123"
    run.mkdir()
    envelope = {
        **_request(),
        "reviewed_at": "2026-08-13T12:34:56+00:00",
    }

    output = import_human_decision_envelope(
        run,
        envelope,
        expected_packet_hash="a" * 64,
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["run_id"] == run.name
    assert saved["packet_hash"] == "a" * 64

    with pytest.raises(FileExistsError):
        import_human_decision_envelope(
            run,
            envelope,
            expected_packet_hash="a" * 64,
        )

    with pytest.raises(ValueError, match="packet_hash"):
        import_human_decision_envelope(
            run,
            {**envelope, "reviewed_at": "2026-08-13T12:34:57+00:00"},
            expected_packet_hash="b" * 64,
        )
