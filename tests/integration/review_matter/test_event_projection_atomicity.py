import pytest

from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.events import MatterEvent, append_matter_event
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
    )
    invalidate_source_dependents(
        store,
        "MATTER-001",
        registered.revision,
        "SOURCE-001",
        "d" * 64,
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
        },
    )
