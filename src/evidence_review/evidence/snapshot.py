"""Canonical hashing and row counts for evidence snapshots."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from evidence_review.canonical_json import sha256_json
from evidence_review.evidence.schema_version import detect_schema_version
from evidence_review.evidence.store import EvidenceStore

SNAPSHOT_TABLES = (
    "documents",
    "revisions",
    "pages",
    "elements",
    "clauses",
    "tables",
    "visuals",
    "links",
    "review_flags",
)


def snapshot_counts(store: EvidenceStore) -> dict[str, int]:
    return {
        table: int(store.scalar(f"SELECT COUNT(*) FROM {table}") or 0)
        for table in SNAPSHOT_TABLES
    }


def compute_snapshot_hash(store: EvidenceStore) -> str:
    """Hash canonical physical database content independent of location."""
    connection = store.require_connection()
    payload: dict[str, list[dict[str, Any]]] = {}
    for table in SNAPSHOT_TABLES:
        columns = [
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        order_column = "id" if "id" in columns else columns[0]
        rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order_column}").fetchall()
        payload[table] = [
            {column: row[column] for column in columns}
            for row in rows
        ]
    return sha256_json(payload)


def _dict_rows(
    connection: sqlite3.Connection,
    query: str,
    columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [
        {column: row[index] for index, column in enumerate(columns)}
        for row in connection.execute(query).fetchall()
    ]


def _json_document(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("stored JSON value must be text or null")
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("stored JSON value is invalid") from error


def _bbox_document(value: object) -> list[float] | None:
    payload = _json_document(value)
    if payload is None:
        return None
    if not isinstance(payload, list) or len(payload) != 4:
        raise ValueError("stored bbox must contain four numbers")
    normalized: list[float] = []
    for item in payload:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("stored bbox must contain four numbers")
        normalized.append(float(item))
    return normalized


def _common_logical_rows(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    return {
        "documents": _dict_rows(
            connection,
            "SELECT id, title FROM documents ORDER BY id",
            ("id", "title"),
        ),
        "revisions": _dict_rows(
            connection,
            """
            SELECT id, document_id, source_hash, byte_size, page_count
            FROM revisions ORDER BY id
            """,
            ("id", "document_id", "source_hash", "byte_size", "page_count"),
        ),
        "pages": _dict_rows(
            connection,
            """
            SELECT id, revision_id, page_number, width, height
            FROM pages ORDER BY id
            """,
            ("id", "revision_id", "page_number", "width", "height"),
        ),
        "clauses": _dict_rows(
            connection,
            """
            SELECT id, revision_id, title, raw_text, normalized_text, review_status
            FROM clauses ORDER BY id
            """,
            (
                "id",
                "revision_id",
                "title",
                "raw_text",
                "normalized_text",
                "review_status",
            ),
        ),
        "links": _dict_rows(
            connection,
            """
            SELECT id, source_id, target_id, relation_type
            FROM links ORDER BY id
            """,
            ("id", "source_id", "target_id", "relation_type"),
        ),
        "review_flags": _dict_rows(
            connection,
            """
            SELECT id, evidence_id, code, status, detail
            FROM review_flags ORDER BY id
            """,
            ("id", "evidence_id", "code", "status", "detail"),
        ),
    }


def _logical_elements(
    connection: sqlite3.Connection,
    version: int,
) -> list[dict[str, Any]]:
    if version == 1:
        rows = connection.execute(
            """
            SELECT e.id, e.page_id, e.revision_id, e.page_number,
                   p.revision_id, p.page_number, e.element_type, e.raw_json,
                   e.raw_text, e.normalized_text, e.raw_payload_hash,
                   e.bbox_json, e.parser_order
            FROM elements e
            LEFT JOIN pages p ON p.id = e.page_id
            ORDER BY e.id
            """
        ).fetchall()
        logical = []
        for row in rows:
            if row[4] is None:
                raise ValueError(f"PAGE_REFERENCE_NOT_FOUND: {row[1]}")
            if row[2] != row[4] or row[3] != row[5]:
                raise ValueError(f"PAGE_REFERENCE_MISMATCH: {row[0]}")
            logical.append(
                {
                    "id": row[0],
                    "page_id": row[1],
                    "revision_id": row[4],
                    "page_number": row[5],
                    "element_type": row[6],
                    "raw_json": _json_document(row[7]),
                    "raw_text": row[8],
                    "normalized_text": row[9],
                    "raw_payload_hash": row[10],
                    "bbox": _bbox_document(row[11]),
                    "parser_order": row[12],
                }
            )
        return logical
    rows = connection.execute(
        """
        SELECT e.id, e.page_id, p.revision_id, p.page_number,
               e.element_type, e.raw_json, e.raw_text, e.normalized_text,
               e.raw_payload_hash, e.bbox_json, e.parser_order
        FROM elements e
        JOIN pages p ON p.id = e.page_id
        ORDER BY e.id
        """
    ).fetchall()
    return [
        {
            "id": row[0],
            "page_id": row[1],
            "revision_id": row[2],
            "page_number": row[3],
            "element_type": row[4],
            "raw_json": _json_document(row[5]),
            "raw_text": row[6],
            "normalized_text": row[7],
            "raw_payload_hash": row[8],
            "bbox": _bbox_document(row[9]),
            "parser_order": row[10],
        }
        for row in rows
    ]


def _logical_tables(
    connection: sqlite3.Connection,
    version: int,
) -> list[dict[str, Any]]:
    if version == 1:
        rows = connection.execute(
            """
            SELECT t.id, t.revision_id, t.page_number, p.id, p.revision_id,
                   p.page_number, t.bbox_json, t.raw_json, t.normalized_json
            FROM tables t
            LEFT JOIN pages p
              ON p.revision_id = t.revision_id AND p.page_number = t.page_number
            ORDER BY t.id
            """
        ).fetchall()
        logical = []
        for row in rows:
            if row[3] is None:
                raise ValueError(
                    f"PAGE_REFERENCE_NOT_FOUND: {row[1]} page {row[2]}"
                )
            logical.append(
                {
                    "id": row[0],
                    "page_id": row[3],
                    "revision_id": row[4],
                    "page_number": row[5],
                    "bbox": _bbox_document(row[6]),
                    "raw_json": _json_document(row[7]),
                    "normalized_json": _json_document(row[8]),
                }
            )
        return logical
    rows = connection.execute(
        """
        SELECT t.id, t.page_id, p.revision_id, p.page_number,
               t.bbox_json, t.raw_json, t.normalized_json
        FROM tables t
        JOIN pages p ON p.id = t.page_id
        ORDER BY t.id
        """
    ).fetchall()
    return [
        {
            "id": row[0],
            "page_id": row[1],
            "revision_id": row[2],
            "page_number": row[3],
            "bbox": _bbox_document(row[4]),
            "raw_json": _json_document(row[5]),
            "normalized_json": _json_document(row[6]),
        }
        for row in rows
    ]


def _logical_visuals(
    connection: sqlite3.Connection,
    version: int,
) -> list[dict[str, Any]]:
    if version == 1:
        rows = connection.execute(
            """
            SELECT v.id, v.revision_id, v.page_number, p.id, p.revision_id,
                   p.page_number, v.kind, v.relative_path, v.sha256,
                   v.bbox_json, v.duplicate_group
            FROM visuals v
            LEFT JOIN pages p
              ON p.revision_id = v.revision_id AND p.page_number = v.page_number
            ORDER BY v.id
            """
        ).fetchall()
        logical = []
        for row in rows:
            if row[3] is None:
                raise ValueError(
                    f"PAGE_REFERENCE_NOT_FOUND: {row[1]} page {row[2]}"
                )
            logical.append(
                {
                    "id": row[0],
                    "page_id": row[3],
                    "revision_id": row[4],
                    "page_number": row[5],
                    "kind": row[6],
                    "relative_path": row[7],
                    "sha256": row[8],
                    "bbox": _bbox_document(row[9]),
                    "duplicate_group": row[10],
                }
            )
        return logical
    rows = connection.execute(
        """
        SELECT v.id, v.page_id, p.revision_id, p.page_number, v.kind,
               v.relative_path, v.sha256, v.bbox_json, v.duplicate_group
        FROM visuals v
        JOIN pages p ON p.id = v.page_id
        ORDER BY v.id
        """
    ).fetchall()
    return [
        {
            "id": row[0],
            "page_id": row[1],
            "revision_id": row[2],
            "page_number": row[3],
            "kind": row[4],
            "relative_path": row[5],
            "sha256": row[6],
            "bbox": _bbox_document(row[7]),
            "duplicate_group": row[8],
        }
        for row in rows
    ]


def compute_logical_snapshot_hash(connection: sqlite3.Connection) -> str:
    """Hash logical evidence rows independent of v1/v2 physical layout."""
    version = detect_schema_version(connection)
    payload = _common_logical_rows(connection)
    payload["elements"] = _logical_elements(connection, version)
    payload["tables"] = _logical_tables(connection, version)
    payload["visuals"] = _logical_visuals(connection, version)
    return sha256_json(payload)
