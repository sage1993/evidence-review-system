from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from evidence_review.canonical_json import dump_bytes
from tests.integration.review_matter.test_legacy_run_reference import _finalized_legacy_run


def test_legacy_run_reference_rejects_noncanonical_human_decision(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    packet_sha256 = hashlib.sha256(
        (run_directory / "final-review-packet.json").read_bytes()
    ).hexdigest()
    decisions = run_directory / "human-decisions"
    decisions.mkdir()
    (decisions / "20260911T090000000000+0000-reviewer-01.json").write_bytes(
        (
            '{"decision":"SATISFIED","notes":"","packet_hash":"'
            + packet_sha256
            + '","reviewed_at":"2026-09-11T09:00:00+00:00",'
            '"reviewer_id":"reviewer-01","run_id":"'
            + run_directory.name
            + '","unexpected":true}'
        ).encode("utf-8")
    )

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)


def test_legacy_run_reference_is_immutable_and_deterministic(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)

    first = legacy_reference_from_run(run_directory)
    second = legacy_reference_from_run(Path(run_directory))

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.run_id = "RUN-00000000000000000000"  # type: ignore[misc]


def test_legacy_run_reference_rejects_noncanonical_packet_without_rewriting(
    tmp_path: Path,
) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    packet_path = run_directory / "final-review-packet.json"
    tampered = packet_path.read_bytes() + b"\n"
    packet_path.write_bytes(tampered)

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)

    assert packet_path.read_bytes() == tampered


def test_legacy_run_reference_rejects_decision_for_another_packet(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    decisions = run_directory / "human-decisions"
    decisions.mkdir()
    (decisions / "20260911T090000000000+0000-reviewer-01.json").write_bytes(
        dump_bytes(
            {
                "run_id": run_directory.name,
                "reviewer_id": "reviewer-01",
                "reviewed_at": "2026-09-11T09:00:00+00:00",
                "packet_hash": "f" * 64,
                "decision": "SATISFIED",
                "notes": "",
            }
        )
    )

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)
