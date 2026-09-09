from __future__ import annotations

from pathlib import Path

import pytest


def test_matter_edit_between_snapshot_read_and_commit_aborts_without_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    from tests.unit.review_matter.test_formalization_snapshot import (
        _evidence_database,
        _matter_store,
    )

    evidence_db = tmp_path / "evidence.sqlite"
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(tmp_path / "matter.sqlite", provenance)
    import evidence_review.review_matter.snapshot as module

    original = module.finalized_evidence_provenance
    mutated = False

    def mutate_before_commit(path: Path) -> dict[str, object]:
        nonlocal mutated
        result = original(path)
        if not mutated:
            mutated = True
            store.rename("MATTER-SNAP-1", expected_revision=2, title="Changed during snapshot")
        return result

    monkeypatch.setattr(module, "finalized_evidence_provenance", mutate_before_commit)

    with pytest.raises(ValueError, match="MATTER_CHANGED_DURING_FORMALIZATION"):
        module.create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)

    assert module.list_formalization_snapshots(store) == ()
    assert store.load("MATTER-SNAP-1").revision == 3
