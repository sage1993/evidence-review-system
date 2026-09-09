import sqlite3

import pytest

from evidence_review.review_matter.events import MatterEvent
from evidence_review.review_matter.store import (
    MatterAlreadyExists,
    MatterRevisionConflict,
    MatterSchemaError,
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


@pytest.mark.parametrize("metadata_value", [None, "not-v1"])
def test_invalid_v1_metadata_migration_rolls_back_without_schema_changes(
    tmp_path, metadata_value
) -> None:
    database = tmp_path / f"invalid-v1-{metadata_value or 'missing'}.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "CREATE TABLE matter_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        if metadata_value is not None:
            connection.execute(
                "INSERT INTO matter_meta(key, value) VALUES ('schema_version', ?)",
                (metadata_value,),
            )

    with pytest.raises(MatterSchemaError):
        MatterStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        row = connection.execute(
            "SELECT value FROM matter_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert (None if row is None else row[0]) == metadata_value
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'formalization_snapshots'"
            ).fetchone()
            is None
        )


@pytest.mark.parametrize("database_version", [1, 2])
def test_malformed_snapshot_table_rejects_without_partial_schema_change(
    tmp_path, database_version
) -> None:
    database = tmp_path / f"malformed-snapshots-v{database_version}.sqlite"
    if database_version == 1:
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA user_version = 1")
            connection.execute(
                "CREATE TABLE matter_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO matter_meta(key, value) VALUES ('schema_version', '1')"
            )
    else:
        store = MatterStore(database)
        store.close()

    with sqlite3.connect(database) as connection:
        if database_version == 2:
            connection.execute("DROP TABLE formalization_snapshots")
        connection.execute(
            """
            CREATE TABLE formalization_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                matter_revision INTEGER NOT NULL,
                canonical_document BLOB NOT NULL
            )
            """
        )
        malformed_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'formalization_snapshots'"
        ).fetchone()[0]

    with pytest.raises(MatterSchemaError, match="MATTER_SNAPSHOT_SCHEMA_INVALID"):
        MatterStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == database_version
        assert (
            connection.execute(
                "SELECT value FROM matter_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            == str(database_version)
        )
        assert (
            connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'formalization_snapshots'"
            ).fetchone()[0]
            == malformed_sql
        )


def test_partial_snapshot_identity_index_rejects_without_schema_change(tmp_path) -> None:
    database = tmp_path / "partial-snapshot-identity.sqlite"
    store = MatterStore(database)
    store.close()

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE formalization_snapshots")
        connection.execute(
            """
            CREATE TABLE formalization_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                matter_revision INTEGER NOT NULL CHECK (matter_revision >= 1),
                canonical_document BLOB NOT NULL,
                FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE RESTRICT
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX partial_snapshot_identity
            ON formalization_snapshots(matter_id, matter_revision)
            WHERE matter_revision >= 1
            """
        )
        index_row = connection.execute(
            'PRAGMA index_list("formalization_snapshots")'
        ).fetchone()
        assert index_row[2] == 1
        assert index_row[4] == 1
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'formalization_snapshots'"
        ).fetchone()[0]
        index_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND name = 'partial_snapshot_identity'"
        ).fetchone()[0]

    with pytest.raises(MatterSchemaError, match="MATTER_SNAPSHOT_SCHEMA_INVALID"):
        MatterStore(database)

    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'formalization_snapshots'"
            ).fetchone()[0]
            == table_sql
        )
        assert (
            connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' AND name = 'partial_snapshot_identity'"
            ).fetchone()[0]
            == index_sql
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT value FROM matter_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            == "2"
        )
