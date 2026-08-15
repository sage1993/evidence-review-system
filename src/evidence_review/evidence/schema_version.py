"""Evidence database schema-version detection and open policy."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 4


class SchemaUpgradeRequired(RuntimeError):
    """Raised when a recognized older evidence schema requires migration."""


class UnsupportedSchemaVersion(RuntimeError):
    """Raised when an evidence database schema is unknown or too new."""


_COMMON_COLUMNS: dict[str, tuple[str, ...]] = {
    "documents": ("id", "title"),
    "revisions": (
        "id",
        "document_id",
        "source_hash",
        "byte_size",
        "page_count",
    ),
    "pages": ("id", "revision_id", "page_number", "width", "height"),
    "clauses": (
        "id",
        "revision_id",
        "title",
        "raw_text",
        "normalized_text",
        "review_status",
    ),
    "links": ("id", "source_id", "target_id", "relation_type"),
    "review_flags": ("id", "evidence_id", "code", "status", "detail"),
    "snapshot_meta": ("key", "value"),
    "retrieval_meta": ("key", "value"),
}

_V1_COLUMNS: dict[str, tuple[str, ...]] = {
    **_COMMON_COLUMNS,
    "elements": (
        "id",
        "revision_id",
        "page_id",
        "page_number",
        "element_type",
        "raw_json",
        "raw_text",
        "normalized_text",
        "raw_payload_hash",
        "bbox_json",
        "parser_order",
    ),
    "tables": (
        "id",
        "revision_id",
        "page_number",
        "bbox_json",
        "raw_json",
        "normalized_json",
    ),
    "visuals": (
        "id",
        "revision_id",
        "page_number",
        "kind",
        "relative_path",
        "sha256",
        "bbox_json",
        "duplicate_group",
    ),
    "retrieval_records": (
        "evidence_id",
        "evidence_type",
        "document_id",
        "revision_id",
        "page_number",
        "bbox_json",
        "source_hash",
        "title",
        "raw_text",
        "normalized_text",
    ),
}

_V2_COLUMNS: dict[str, tuple[str, ...]] = {
    **_COMMON_COLUMNS,
    "schema_meta": ("key", "value"),
    "elements": (
        "id",
        "page_id",
        "element_type",
        "raw_json",
        "raw_text",
        "normalized_text",
        "raw_payload_hash",
        "bbox_json",
        "parser_order",
    ),
    "tables": (
        "id",
        "page_id",
        "bbox_json",
        "raw_json",
        "normalized_json",
    ),
    "visuals": (
        "id",
        "page_id",
        "kind",
        "relative_path",
        "sha256",
        "bbox_json",
        "duplicate_group",
    ),
    "retrieval_records": (
        "evidence_id",
        "evidence_type",
        "document_id",
        "revision_id",
        "page_id",
        "page_number",
        "bbox_json",
        "source_hash",
        "title",
        "raw_text",
        "normalized_text",
    ),
}

_V3_COLUMNS: dict[str, tuple[str, ...]] = {
    **_COMMON_COLUMNS,
    "pages": (
        "id",
        "revision_id",
        "page_number",
        "width",
        "height",
        "origin_x",
        "origin_y",
        "rotation",
        "box_kind",
    ),
    "schema_meta": ("key", "value"),
    "elements": (
        "id",
        "page_id",
        "element_type",
        "raw_json",
        "raw_text",
        "normalized_text",
        "raw_payload_hash",
        "bbox_json",
        "parser_order",
    ),
    "tables": (
        "id",
        "page_id",
        "bbox_json",
        "raw_json",
        "normalized_json",
    ),
    "visuals": (
        "id",
        "page_id",
        "kind",
        "relative_path",
        "sha256",
        "bbox_json",
        "duplicate_group",
    ),
    "retrieval_records": (
        "evidence_id",
        "evidence_type",
        "document_id",
        "revision_id",
        "page_id",
        "page_number",
        "bbox_json",
        "source_hash",
        "title",
        "raw_text",
        "normalized_text",
    ),
}

_V4_COLUMNS: dict[str, tuple[str, ...]] = {
    **_V3_COLUMNS,
    "clause_retrieval_records": (
        "clause_id",
        "document_id",
        "revision_id",
        "title",
        "chapter",
        "section",
        "clause_number",
        "raw_text",
        "normalized_text",
    ),
    "clause_evidence_links": (
        "clause_id",
        "evidence_id",
        "relation_type",
    ),
}

_EVIDENCE_FTS_TABLES = {
    "evidence_fts",
    "evidence_fts_config",
    "evidence_fts_content",
    "evidence_fts_data",
    "evidence_fts_docsize",
    "evidence_fts_idx",
}
_CLAUSE_FTS_TABLES = {
    "clause_fts",
    "clause_fts_config",
    "clause_fts_content",
    "clause_fts_data",
    "clause_fts_docsize",
    "clause_fts_idx",
}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    )


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
    }


def _is_exact_shape(
    connection: sqlite3.Connection,
    expected: dict[str, tuple[str, ...]],
    *,
    fts_tables: set[str],
) -> bool:
    for table, expected_columns in expected.items():
        if not _table_exists(connection, table):
            return False
        if _columns(connection, table) != expected_columns:
            return False
    if not all(_table_exists(connection, table) for table in fts_tables):
        return False
    return _table_names(connection) == set(expected) | fts_tables


def detect_schema_version(connection: sqlite3.Connection) -> int:
    """Return the recognized evidence schema version for an open connection."""
    if _table_exists(connection, "schema_meta"):
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise UnsupportedSchemaVersion("unrecognized evidence schema metadata")
        try:
            version = int(row[0])
        except (TypeError, ValueError) as error:
            raise UnsupportedSchemaVersion(
                "unrecognized evidence schema metadata"
            ) from error
        if version < 1:
            raise UnsupportedSchemaVersion(
                f"unsupported evidence schema version: {version}"
            )
        if version == 1:
            raise UnsupportedSchemaVersion(
                "schema version 1 metadata does not match the recognized legacy shape"
            )
        if version == 2 and not _is_exact_shape(
            connection,
            _V2_COLUMNS,
            fts_tables=_EVIDENCE_FTS_TABLES,
        ):
            raise UnsupportedSchemaVersion("evidence schema version 2 shape is invalid")
        if version == 3 and not _is_exact_shape(
            connection,
            _V3_COLUMNS,
            fts_tables=_EVIDENCE_FTS_TABLES,
        ):
            raise UnsupportedSchemaVersion("evidence schema version 3 shape is invalid")
        if version == 4 and not _is_exact_shape(
            connection,
            _V4_COLUMNS,
            fts_tables=_EVIDENCE_FTS_TABLES | _CLAUSE_FTS_TABLES,
        ):
            raise UnsupportedSchemaVersion("evidence schema version 4 shape is invalid")
        return version

    if _is_exact_shape(
        connection,
        _V1_COLUMNS,
        fts_tables=_EVIDENCE_FTS_TABLES,
    ):
        return 1

    raise UnsupportedSchemaVersion("unrecognized evidence schema")


def require_current_schema(connection: sqlite3.Connection) -> None:
    """Require the current evidence schema without mutating the database."""
    version = detect_schema_version(connection)
    if version in (1, 2, 3):
        raise SchemaUpgradeRequired(
            f"database uses schema version {version}; explicit migration is required"
        )
    if version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            f"unsupported evidence schema version: {version}"
        )
