import pytest

from evidence_review.canonical_json import dumps
from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.events import (
    MatterEvent,
    append_matter_event,
    matter_event_document,
)
from evidence_review.review_matter.invalidation import (
    invalidate_source_dependents,
    register_issue_source_dependency,
)
from evidence_review.review_matter.store import MatterStore


def test_event_and_projection_roll_back_together(tmp_path, monkeypatch) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Initial")
    event = MatterEvent(kind="TITLE_CHANGED", payload={"title": "Changed"})
    monkeypatch.setattr(
        store,
        "apply_projection",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError, match="boom"):
        append_matter_event(store, "MATTER-001", expected_revision=1, event=event)
    assert store.load("MATTER-001").revision == 1
    assert store.list_events("MATTER-001") == ()


def test_projection_rebuild_replays_append_only_events(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Initial")
    append_matter_event(
        store,
        "MATTER-001",
        expected_revision=1,
        event=MatterEvent(kind="TITLE_CHANGED", payload={"title": "Changed"}),
    )
    rebuilt = store.rebuild_projection("MATTER-001")
    assert rebuilt.revision == 2
    assert rebuilt.title == "Changed"


def test_projection_rebuild_restores_event_owned_metadata(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    append_matter_event(
        store,
        "MATTER-001",
        expected_revision=1,
        event=MatterEvent(
            kind="EVIDENCE_BOUND",
            payload={
                "evidence_snapshot_hash": "a" * 64,
                "evidence_db_sha256": "b" * 64,
                "schema_version": 4,
                "bound_revision": 2,
            },
        ),
    )
    registered = register_issue_source_dependency(
        store,
        "MATTER-001",
        2,
        "ISSUE-001",
        "SOURCE-001",
        "c" * 64,
        "REV-1",
    )
    invalidate_source_dependents(
        store,
        "MATTER-001",
        registered.revision,
        "SOURCE-001",
        "d" * 64,
        "REV-2",
    )

    with store.transaction():
        store.connection.execute(
            "DELETE FROM matter_evidence_bindings WHERE matter_id = ?",
            ("MATTER-001",),
        )
        store.connection.execute(
            "DELETE FROM matter_source_dependencies WHERE matter_id = ?",
            ("MATTER-001",),
        )

    rebuilt = store.rebuild_projection("MATTER-001")
    assert rebuilt.issues[0].work_state == "STALE"
    assert store.get_evidence_binding("MATTER-001") == {
        "evidence_snapshot_hash": "a" * 64,
        "evidence_db_sha256": "b" * 64,
        "schema_version": 4,
        "bound_revision": 2,
    }
    assert store.list_source_dependencies("MATTER-001") == (
        {
            "issue_id": "ISSUE-001",
            "source_key": "SOURCE-001",
            "source_hash": "d" * 64,
            "source_revision_id": "REV-2",
        },
    )


def test_direct_source_dependency_event_is_validated_before_append(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    event = MatterEvent(
        kind="SOURCE_DEPENDENCY_REGISTERED",
        payload={
            "issue_id": "ISSUE-001",
            "source_key": "SOURCE-001",
            "source_hash": "not-a-sha256",
            "source_revision_id": "REV-1",
        },
    )

    with pytest.raises(ValueError):
        append_matter_event(store, "MATTER-001", expected_revision=1, event=event)
    assert store.load("MATTER-001").revision == 1
    assert store.list_source_dependencies("MATTER-001") == ()
    assert store.list_events("MATTER-001") == ()


def test_rebuild_rejects_malformed_invalidation_before_side_effects(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    event = MatterEvent(
        kind="ISSUES_INVALIDATED",
        payload={
            "issue_ids": ["ISSUE-001"],
            "source_key": "SOURCE-001",
            "new_source_hash": "not-a-sha256",
            "new_source_revision_id": "REV-2",
        },
    )
    with store.transaction():
        store.connection.execute(
            """
            INSERT INTO matter_events(matter_id, sequence, matter_revision, event_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                "MATTER-001",
                1,
                2,
                dumps(matter_event_document(event)),
            ),
        )

    with pytest.raises(ValueError):
        store.rebuild_projection("MATTER-001")
    assert store.load("MATTER-001").revision == 1
    assert store.list_source_dependencies("MATTER-001") == ()
