"""Canonical hashing and row counts for evidence snapshots."""
from __future__ import annotations

from typing import Any

from ansim_review.canonical_json import sha256_json
from ansim_review.evidence.store import EvidenceStore

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
    """Hash canonical database content independent of filesystem location."""
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
