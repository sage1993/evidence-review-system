from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from evidence_review.review_matter.formal_run_binding import (
    bind_formal_run,
    list_formal_runs,
)
from evidence_review.review_matter.snapshot import create_formalization_snapshot


def _matter_with_two_snapshots(tmp_path: Path):
    from tests.unit.review_matter.test_formalization_snapshot import (
        _evidence_database,
        _matter_store,
    )

    evidence_db = tmp_path / "evidence.sqlite"
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(tmp_path / "matter.sqlite", provenance)
    first = create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)
    store.rename("MATTER-SNAP-1", expected_revision=2, title="Revised snapshot review")
    second = create_formalization_snapshot(store, "MATTER-SNAP-1", 3, evidence_db)
    return store, first, second


def test_one_matter_binds_two_immutable_runs_in_revision_order_without_packet_overwrite(
    tmp_path: Path,
) -> None:
    store, first, second = _matter_with_two_snapshots(tmp_path)
    runs = tmp_path / "runs"
    first_packet = runs / "RUN-11111111111111111111" / "final-review-packet.json"
    second_packet = runs / "RUN-22222222222222222222" / "final-review-packet.json"
    first_packet.parent.mkdir(parents=True)
    second_packet.parent.mkdir(parents=True)
    first_packet.write_bytes(b"first immutable packet")
    second_packet.write_bytes(b"second immutable packet")
    first_hash = hashlib.sha256(first_packet.read_bytes()).hexdigest()
    second_hash = hashlib.sha256(second_packet.read_bytes()).hexdigest()

    first_binding = bind_formal_run(
        store, "MATTER-SNAP-1", first.snapshot_id, "RUN-11111111111111111111", first_hash
    )
    second_binding = bind_formal_run(
        store, "MATTER-SNAP-1", second.snapshot_id, "RUN-22222222222222222222", second_hash
    )

    assert list_formal_runs(store, "MATTER-SNAP-1") == (first_binding, second_binding)
    assert first_packet.read_bytes() == b"first immutable packet"
    assert second_packet.read_bytes() == b"second immutable packet"


def test_formal_run_lineage_rejects_duplicate_and_conflicting_append_attempts(
    tmp_path: Path,
) -> None:
    store, first, second = _matter_with_two_snapshots(tmp_path)
    packet_hash = "a" * 64
    bind_formal_run(
        store, "MATTER-SNAP-1", first.snapshot_id, "RUN-11111111111111111111", packet_hash
    )

    with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_ALREADY_EXISTS"):
        bind_formal_run(
            store, "MATTER-SNAP-1", first.snapshot_id, "RUN-11111111111111111111", packet_hash
        )
    with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_ALREADY_EXISTS"):
        bind_formal_run(
            store, "MATTER-SNAP-1", first.snapshot_id, "RUN-11111111111111111111", "b" * 64
        )
    with pytest.raises(ValueError, match="FORMAL_RUN_BINDING_ALREADY_EXISTS"):
        bind_formal_run(
            store, "MATTER-SNAP-1", second.snapshot_id, "RUN-11111111111111111111", packet_hash
        )

    assert [item.snapshot_id for item in list_formal_runs(store, "MATTER-SNAP-1")] == [
        first.snapshot_id
    ]
