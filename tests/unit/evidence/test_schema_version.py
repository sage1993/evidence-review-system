from pathlib import Path
import sqlite3

import pytest

from ansim_review.evidence.schema_version import (
    SchemaUpgradeRequired,
    UnsupportedSchemaVersion,
    detect_schema_version,
    require_current_schema,
)


V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")


def create_v1_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    return connection


def test_missing_schema_meta_with_exact_v1_shape_is_version_one(tmp_path: Path) -> None:
    connection = create_v1_database(tmp_path / "v1.sqlite")
    try:
        assert detect_schema_version(connection) == 1
    finally:
        connection.close()


def test_schema_meta_reports_version_two(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "v2.sqlite")
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
        assert detect_schema_version(connection) == 2
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
