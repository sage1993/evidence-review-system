from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from evidence_review.evidence.schema_version import (
    SCHEMA_VERSION,
    SchemaUpgradeRequired,
    detect_schema_version,
    require_current_schema,
)

CURRENT_SCHEMA = Path("src/evidence_review/evidence/schema.sql")
V3_SCHEMA = Path("src/evidence_review/evidence/schema_v3.sql")


def _create(path: Path, schema: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(schema.read_text(encoding="utf-8"))
    return connection


def test_current_schema_is_v4_with_separate_clause_semantic_index(tmp_path: Path) -> None:
    connection = _create(tmp_path / "v4.sqlite", CURRENT_SCHEMA)
    try:
        assert SCHEMA_VERSION == 4
        assert detect_schema_version(connection) == 4
        require_current_schema(connection)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "clause_retrieval_records" in tables
        assert "clause_evidence_links" in tables
        assert "clause_fts" in tables
    finally:
        connection.close()


def test_v3_requires_explicit_upgrade_after_v4_release(tmp_path: Path) -> None:
    connection = _create(tmp_path / "v3.sqlite", V3_SCHEMA)
    try:
        assert detect_schema_version(connection) == 3
        with pytest.raises(SchemaUpgradeRequired, match="schema version 3"):
            require_current_schema(connection)
    finally:
        connection.close()


def test_v4_shape_rejects_missing_clause_relation_table(tmp_path: Path) -> None:
    connection = _create(tmp_path / "invalid-v4.sqlite", CURRENT_SCHEMA)
    connection.execute("DROP TABLE clause_evidence_links")
    try:
        with pytest.raises(Exception, match="shape"):
            detect_schema_version(connection)
    finally:
        connection.close()
