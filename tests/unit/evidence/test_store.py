import sqlite3
from pathlib import Path

import pytest

from ansim_review.evidence.schema_version import (
    SCHEMA_VERSION,
    SchemaUpgradeRequired,
    UnsupportedSchemaVersion,
)
from ansim_review.evidence.store import EvidenceStore

V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")


def test_missing_database_requires_explicit_create(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        with EvidenceStore(path):
            pass
    assert not path.exists()


def test_explicit_create_builds_schema_v2(tmp_path: Path) -> None:
    path = tmp_path / "created.sqlite"
    with EvidenceStore(path, create=True) as store:
        version = store.scalar(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        )
        assert version == str(SCHEMA_VERSION)
    assert path.is_file()


def test_explicit_create_refuses_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "existing.sqlite"
    path.write_bytes(b"already exists")
    with pytest.raises(FileExistsError):
        with EvidenceStore(path, create=True):
            pass
    assert path.read_bytes() == b"already exists"


def test_opening_v1_requires_migration_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "v1.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    connection.close()
    before = path.read_bytes()

    with pytest.raises(SchemaUpgradeRequired):
        with EvidenceStore(path):
            pass

    assert path.read_bytes() == before


def test_opening_existing_v2_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite"
    with EvidenceStore(path, create=True):
        pass
    with EvidenceStore(path) as store:
        assert store.scalar("SELECT COUNT(*) FROM documents") == 0


def test_newer_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "newer.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '99');
        """
    )
    connection.close()

    with pytest.raises(UnsupportedSchemaVersion, match="99"):
        with EvidenceStore(path):
            pass
