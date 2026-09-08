from threading import Barrier, Thread

import pytest

from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def test_stale_writer_cannot_overwrite_newer_matter_revision(tmp_path) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    created = store.create(matter_id="MATTER-001", title="Initial")
    assert created.revision == 1
    updated = store.rename("MATTER-001", expected_revision=1, title="Writer A")
    assert updated.revision == 2
    with pytest.raises(MatterRevisionConflict, match="MATTER_REVISION_CONFLICT"):
        store.rename("MATTER-001", expected_revision=1, title="Writer B")
    assert store.load("MATTER-001").title == "Writer A"


def test_two_sqlite_writers_allow_only_one_compare_and_swap(tmp_path) -> None:
    database = tmp_path / "review-matters.sqlite"
    MatterStore(database).create(matter_id="MATTER-001", title="Initial")
    barrier = Barrier(2)
    outcomes: list[str] = []

    def writer(title: str) -> None:
        store = MatterStore(database)
        try:
            barrier.wait()
            try:
                outcomes.append(store.rename("MATTER-001", 1, title).title)
            except MatterRevisionConflict:
                outcomes.append("CONFLICT")
        finally:
            store.close()

    first = Thread(target=writer, args=("Writer A",))
    second = Thread(target=writer, args=("Writer B",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert sorted(outcomes) == ["CONFLICT", "Writer A"] or sorted(outcomes) == [
        "CONFLICT",
        "Writer B",
    ]
