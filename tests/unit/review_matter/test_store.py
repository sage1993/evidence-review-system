import pytest

from evidence_review.review_matter.events import MatterEvent
from evidence_review.review_matter.store import (
    MatterAlreadyExists,
    MatterRevisionConflict,
    MatterStore,
)


def test_store_creates_and_renames_one_matter(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    created = store.create(matter_id="MATTER-001", title="Initial")
    assert created.revision == 1
    assert store.load("MATTER-001").title == "Initial"

    updated = store.rename("MATTER-001", expected_revision=1, title="Renamed")
    assert updated.revision == 2
    assert updated.title == "Renamed"


def test_rename_is_preserved_when_projection_is_rebuilt(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Initial")

    store.rename("MATTER-001", expected_revision=1, title="Renamed")

    rebuilt = store.rebuild_projection("MATTER-001")
    assert rebuilt.matter == store.load("MATTER-001")
    assert rebuilt.title == "Renamed"
    assert rebuilt.revision == 2
    assert store.list_events("MATTER-001") == (
        MatterEvent(kind="TITLE_CHANGED", payload={"title": "Renamed"}),
    )


def test_store_rejects_duplicate_matter_without_overwriting(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Initial")
    with pytest.raises(MatterAlreadyExists, match="MATTER_ALREADY_EXISTS"):
        store.create(matter_id="MATTER-001", title="Other")
    assert store.load("MATTER-001").title == "Initial"


def test_stale_revision_conflict_leaves_matter_unchanged(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(matter_id="MATTER-001", title="Initial")
    store.rename("MATTER-001", expected_revision=1, title="Writer A")
    with pytest.raises(MatterRevisionConflict, match="MATTER_REVISION_CONFLICT"):
        store.rename("MATTER-001", expected_revision=1, title="Writer B")
    assert store.load("MATTER-001").title == "Writer A"
