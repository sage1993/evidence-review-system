from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.review_matter.snapshot import create_formalization_snapshot


def _setup_workspace(tmp_path: Path) -> tuple[Path, object, object]:
    from tests.unit.review_matter.test_formalization_snapshot import (
        _evidence_database,
        _matter_store,
    )

    workspace = tmp_path / "workspace"
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    evidence_db.parent.mkdir(parents=True)
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(workspace / "matter.sqlite", provenance)
    snapshot = create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)
    return workspace, store, snapshot


def test_persisted_snapshot_adapts_to_existing_strict_formal_core_without_matter_write(
    tmp_path: Path,
) -> None:
    workspace, store, snapshot = _setup_workspace(tmp_path)
    before_matter = store.load("MATTER-SNAP-1")
    before_events = store.list_events("MATTER-SNAP-1")
    before_bindings = before_matter.source_bindings

    from evidence_review.review_matter.formalization import formalize_snapshot

    prepared = formalize_snapshot(workspace, snapshot)

    assert prepared.status == "WAITING_TRACK_A"
    request_path = workspace / "runs" / prepared.run_id / "review-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["inputs"]["formalization_snapshot_id"] == snapshot.snapshot_id
    assert request["inputs"]["matter_id"] == snapshot.matter_id
    assert request["inputs"]["matter_revision"] == snapshot.matter_revision
    assert len(request["evidence"]) == len(snapshot.selected_evidence)
    assert store.load("MATTER-SNAP-1") == before_matter
    assert store.list_events("MATTER-SNAP-1") == before_events
    assert store.load("MATTER-SNAP-1").source_bindings == before_bindings


def test_same_snapshot_has_same_formal_request_identity(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    first = formalize_snapshot(workspace, snapshot)
    second = formalize_snapshot(workspace, snapshot)

    assert second.run_id == first.run_id
    assert second.status == first.status == "WAITING_TRACK_A"


def test_missing_or_tampered_persisted_snapshot_fails_closed(tmp_path: Path) -> None:
    workspace, store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    store.connection.execute(
        "UPDATE formalization_snapshots SET canonical_document = ? WHERE snapshot_id = ?",
        (b"{}", snapshot.snapshot_id),
    )
    store.connection.commit()

    with pytest.raises(ValueError, match="SNAPSHOT|snapshot"):
        formalize_snapshot(workspace, snapshot)
