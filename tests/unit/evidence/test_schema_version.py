import sqlite3
from pathlib import Path

import pytest

from evidence_review.evidence.schema_version import (
    SchemaUpgradeRequired,
    UnsupportedSchemaVersion,
    detect_schema_version,
    require_current_schema,
)

V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")
V2_SCHEMA = Path("src/evidence_review/evidence/schema_v2.sql")


def create_v1_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    return connection


def create_v2_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(V2_SCHEMA.read_text(encoding="utf-8"))
    return connection


def test_missing_schema_meta_with_exact_v1_shape_is_version_one(tmp_path: Path) -> None:
    connection = create_v1_database(tmp_path / "v1.sqlite")
    try:
        assert detect_schema_version(connection) == 1
    finally:
        connection.close()


def test_exact_v2_shape_reports_version_two(tmp_path: Path) -> None:
    connection = create_v2_database(tmp_path / "v2.sqlite")
    try:
        assert detect_schema_version(connection) == 2
        with pytest.raises(SchemaUpgradeRequired, match="schema version 2"):
            require_current_schema(connection)
    finally:
        connection.close()


def test_exact_v3_shape_reports_current_version(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "v3.sqlite")
    connection.executescript(
        Path("src/evidence_review/evidence/schema.sql").read_text(encoding="utf-8")
    )
    try:
        assert detect_schema_version(connection) == 3
        require_current_schema(connection)
    finally:
        connection.close()

def test_version_one_requires_explicit_upgrade(tmp_path: Path) -> None:
    connection = create_v1_database(tmp_path / "v1.sqlite")
    try:
        with pytest.raises(SchemaUpgradeRequired, match="schema version 1"):
            require_current_schema(connection)
    finally:
        connection.close()


def test_unknown_legacy_shape_is_rejected(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "unknown.sqlite")
    connection.execute("CREATE TABLE documents(id TEXT PRIMARY KEY)")
    try:
        with pytest.raises(UnsupportedSchemaVersion, match="unrecognized"):
            detect_schema_version(connection)
    finally:
        connection.close()


def test_v1_with_unknown_table_is_rejected(tmp_path: Path) -> None:
    connection = create_v1_database(tmp_path / "v1-extra.sqlite")
    connection.execute("CREATE TABLE unexpected(id TEXT PRIMARY KEY)")
    try:
        with pytest.raises(UnsupportedSchemaVersion, match="unrecognized"):
            detect_schema_version(connection)
    finally:
        connection.close()


def test_v2_metadata_without_required_tables_is_rejected(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "v2-incomplete.sqlite")
    connection.executescript(
        """
        CREATE TABLE schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '2');
        """
    )
    try:
        with pytest.raises(UnsupportedSchemaVersion, match="shape"):
            require_current_schema(connection)
    finally:
        connection.close()


def test_v2_with_unknown_table_is_rejected(tmp_path: Path) -> None:
    connection = create_v2_database(tmp_path / "v2-extra.sqlite")
    connection.execute("CREATE TABLE unexpected(id TEXT PRIMARY KEY)")
    try:
        with pytest.raises(UnsupportedSchemaVersion, match="shape"):
            require_current_schema(connection)
    finally:
        connection.close()


def test_newer_schema_version_is_rejected(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "newer.sqlite")
    connection.executescript(
        """
        CREATE TABLE schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '99');
        """
    )
    try:
        with pytest.raises(UnsupportedSchemaVersion, match="99"):
            require_current_schema(connection)
    finally:
        connection.close()
