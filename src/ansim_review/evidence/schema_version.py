"""Evidence database schema-version detection and open policy."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2


class SchemaUpgradeRequired(RuntimeError):
    """Raised when a recognized older evidence schema requires migration."""


class UnsupportedSchemaVersion(RuntimeError):
    """Raised when an evidence database schema is unknown or too new."""


_V1_COLUMNS: dict[str, tuple[str, ...]] = {
    "documents": ("id", "title"),
    "revisions": (
        "id",
        "document_id",
        "source_hash",
        "byte_size",
        "page_count",
    ),
    "pages": ("id", "revision_id", "page_number", "width", "height"),
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
    "clauses": (
        "id",
        "revision_id",
        "title",
        "raw_text",
        "normalized_text",
        "review_status",
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
    "links": ("id", "source_id", "target_id", "relation_type"),
    "review_flags": ("id", "evidence_id", "code", "status", "detail"),
    "snapshot_meta": ("key", "value"),
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
    "retrieval_meta": ("key", "value"),
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


def _is_exact_v1_shape(connection: sqlite3.Connection) -> bool:
    for table, expected_columns in _V1_COLUMNS.items():
        if not _table_exists(connection, table):
            return False
        if _columns(connection, table) != expected_columns:
            return False
    return _table_exists(connection, "evidence_fts")


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
        return version

    if _is_exact_v1_shape(connection):
        return 1

    raise UnsupportedSchemaVersion("unrecognized evidence schema")


def require_current_schema(connection: sqlite3.Connection) -> None:
    """Require the current evidence schema without mutating the database."""
    version = detect_schema_version(connection)
    if version == 1:
        raise SchemaUpgradeRequired(
            "database uses schema version 1; explicit migration is required"
        )
    if version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            f"unsupported evidence schema version: {version}"
        )
