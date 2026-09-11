from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.events import list_matter_events
from evidence_review.review_matter.formal_run_binding import (
    bind_formal_run,
    list_formal_runs,
)
from evidence_review.review_matter.invalidation import (
    invalidate_source_dependents,
    register_issue_source_dependency,
)
from evidence_review.review_matter.service import ReviewMatterService
from evidence_review.review_matter.snapshot import (
    create_formalization_snapshot,
    formalization_snapshot_document,
    list_formalization_snapshots,
)
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def _matter_store(path: Path) -> MatterStore:
    store = MatterStore(path)
    store.create(
        matter_id="MATTER-REV-1",
        title="Revision impact review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-ROOT",
                question="Root issue",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
            MatterIssue(
                issue_id="ISSUE-DOWNSTREAM",
                question="Downstream issue",
                work_state="READY_TO_FORMALIZE",
                depends_on=("ISSUE-ROOT",),
            ),
            MatterIssue(
                issue_id="ISSUE-INDEPENDENT",
                question="Independent issue",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    registered = register_issue_source_dependency(
        store,
        "MATTER-REV-1",
        1,
        "ISSUE-ROOT",
        "SRC-1",
        "a" * 64,
        source_revision_id="REV-1",
    )
    register_issue_source_dependency(
        store,
        "MATTER-REV-1",
        registered.revision,
        "ISSUE-INDEPENDENT",
        "SRC-2",
        "c" * 64,
        source_revision_id="REV-1",
    )
    return store


def test_changed_source_stales_direct_and_transitive_dependents_only(tmp_path: Path) -> None:
    store = _matter_store(tmp_path / "review-matters.sqlite")

    invalidated = invalidate_source_dependents(
        store,
        "MATTER-REV-1",
        3,
        "SRC-1",
        "b" * 64,
        new_source_revision_id="REV-2",
    )

    assert [(issue.issue_id, issue.work_state) for issue in invalidated.issues] == [
        ("ISSUE-ROOT", "STALE"),
        ("ISSUE-DOWNSTREAM", "STALE"),
        ("ISSUE-INDEPENDENT", "READY_TO_FORMALIZE"),
    ]
    assert list_matter_events(store, "MATTER-REV-1")[-1].kind == "ISSUES_INVALIDATED"


def test_stale_revision_conflict_leaves_issue_projection_and_event_history_unchanged(
    tmp_path: Path,
) -> None:
    store = _matter_store(tmp_path / "review-matters.sqlite")
    before = store.load("MATTER-REV-1")
    events_before = list_matter_events(store, "MATTER-REV-1")

    with pytest.raises(MatterRevisionConflict, match="MATTER_REVISION_CONFLICT"):
        invalidate_source_dependents(
            store,
            "MATTER-REV-1",
            2,
            "SRC-1",
            "b" * 64,
            new_source_revision_id="REV-2",
        )

    assert store.load("MATTER-REV-1") == before
    assert list_matter_events(store, "MATTER-REV-1") == events_before


def test_invalidation_preserves_existing_formal_history_and_blocks_new_formalization(
    tmp_path: Path,
) -> None:
    from tests.integration.review_matter.test_multi_run_history import _finalized_formal_run
    from tests.unit.review_matter.test_formalization_snapshot import _evidence_database
    from tests.unit.review_matter.test_formalization_snapshot import (
        _matter_store as create_bound_matter_store,
    )

    workspace = tmp_path / "workspace"
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    evidence_db.parent.mkdir(parents=True)
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = create_bound_matter_store(workspace / "matter.sqlite", provenance)
    registered = register_issue_source_dependency(
        store,
        "MATTER-SNAP-1",
        2,
        "ISSUE-SNAP-1",
        "SRC-SNAP-1",
        "a" * 64,
        source_revision_id="REV-1",
    )
    snapshot = create_formalization_snapshot(
        store, "MATTER-SNAP-1", registered.revision, evidence_db
    )
    run_id, packet_sha256 = _finalized_formal_run(workspace, snapshot)
    binding = bind_formal_run(
        store,
        "MATTER-SNAP-1",
        snapshot.snapshot_id,
        run_id,
        packet_sha256,
        workspace_root=workspace,
    )
    packet_path = workspace / "runs" / run_id / "final-review-packet.json"
    packet_before = packet_path.read_bytes()
    snapshot_before = formalization_snapshot_document(snapshot)

    invalidated = invalidate_source_dependents(
        store,
        "MATTER-SNAP-1",
        registered.revision,
        "SRC-SNAP-1",
        "b" * 64,
        new_source_revision_id="REV-2",
    )

    assert invalidated.issues[0].work_state == "STALE"
    assert list_formalization_snapshots(store) == (snapshot,)
    assert formalization_snapshot_document(snapshot) == snapshot_before
    assert list_formal_runs(store, "MATTER-SNAP-1", workspace_root=workspace) == (binding,)
    assert packet_path.read_bytes() == packet_before
    with pytest.raises(ValueError, match="NOT_READY|STALE|FORMALIZATION"):
        create_formalization_snapshot(
            store, "MATTER-SNAP-1", invalidated.revision, evidence_db
        )


def test_same_hash_changed_source_revision_stales_direct_and_downstream_issues(
    tmp_path: Path,
) -> None:
    store = _matter_store(tmp_path / "review-matters.sqlite")

    invalidated = invalidate_source_dependents(
        store,
        "MATTER-REV-1",
        3,
        "SRC-1",
        "a" * 64,
        new_source_revision_id="REV-2",
    )

    assert [(issue.issue_id, issue.work_state) for issue in invalidated.issues] == [
        ("ISSUE-ROOT", "STALE"),
        ("ISSUE-DOWNSTREAM", "STALE"),
        ("ISSUE-INDEPENDENT", "READY_TO_FORMALIZE"),
    ]
    assert next(
        dependency
        for dependency in store.list_source_dependencies("MATTER-REV-1")
        if dependency["source_key"] == "SRC-1"
    )["source_revision_id"] == "REV-2"


def test_malformed_unrelated_persisted_dependency_stales_all_issues(
    tmp_path: Path,
) -> None:
    store = _matter_store(tmp_path / "review-matters.sqlite")
    store.connection.execute(
        """
        UPDATE matter_source_dependencies
        SET source_hash = ?
        WHERE matter_id = ? AND issue_id = ?
        """,
        ("not-a-sha256", "MATTER-REV-1", "ISSUE-INDEPENDENT"),
    )
    store.connection.commit()

    invalidated = invalidate_source_dependents(
        store,
        "MATTER-REV-1",
        3,
        "SRC-1",
        "b" * 64,
        new_source_revision_id="REV-2",
    )

    assert [issue.work_state for issue in invalidated.issues] == [
        "STALE",
        "STALE",
        "STALE",
    ]


def test_service_facade_invalidates_through_the_existing_matter_event_authority(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _matter_store(workspace / "matter.sqlite")

    invalidated = ReviewMatterService.open(workspace).invalidate_source_dependents(
        matter_id="MATTER-REV-1",
        expected_revision=3,
        source_key="SRC-1",
        new_source_hash="b" * 64,
        new_source_revision_id="REV-2",
    )

    assert invalidated.issues[0].work_state == "STALE"
    assert invalidated.revision == 4
