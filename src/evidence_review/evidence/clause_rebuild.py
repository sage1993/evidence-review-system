"""Backfill deterministic clause artifacts for parser-produced schema-v4 workspaces."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from evidence_review.evidence.clause_materialization import derive_legal_clauses
from evidence_review.evidence.reference_materialization import (
    materialize_legal_reference_links,
)
from evidence_review.retrieval.index import build_fts_index, require_fresh_index


def _source_elements(
    connection: sqlite3.Connection,
    revision_ids: Sequence[str],
) -> tuple[dict[str, object], ...]:
    if not revision_ids:
        return ()
    placeholders = ", ".join("?" for _ in revision_ids)
    rows = connection.execute(
        f"""
        SELECT e.id, p.revision_id, p.page_number, e.parser_order,
               e.raw_text, e.normalized_text
        FROM elements e
        JOIN pages p ON p.id = e.page_id
        WHERE p.revision_id IN ({placeholders})
        ORDER BY p.revision_id, p.page_number, e.parser_order, e.id
        """,
        tuple(revision_ids),
    ).fetchall()
    return tuple(
        {
            "id": str(row[0]),
            "revision_id": str(row[1]),
            "page_number": int(row[2]),
            "parser_order": int(row[3]),
            "raw_text": None if row[4] is None else str(row[4]),
            "normalized_text": None if row[5] is None else str(row[5]),
        }
        for row in rows
    )


def _uncovered_revisions(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT DISTINCT p.revision_id
        FROM elements e
        JOIN pages p ON p.id = e.page_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM clauses c
            WHERE c.revision_id = p.revision_id
        )
        ORDER BY p.revision_id
        """
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _indexable_clause_count(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM clauses
        WHERE COALESCE(normalized_text, raw_text, '') <> ''
        """
    ).fetchone()
    return 0 if row is None else int(row[0])


def _count(connection: sqlite3.Connection, table: str) -> int:
    allowed = {
        "elements",
        "clause_retrieval_records",
        "clause_fts",
    }
    if table not in allowed:
        raise ValueError(f"unsupported table: {table}")
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return 0 if row is None else int(row[0])


def _insert_derived_clauses(
    connection: sqlite3.Connection,
    revision_ids: Sequence[str],
) -> int:
    materialized = derive_legal_clauses(_source_elements(connection, revision_ids))
    if not materialized.clauses:
        return 0

    before = connection.total_changes
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.executemany(
            """
            INSERT OR IGNORE INTO clauses(
                id, revision_id, title, raw_text, normalized_text, review_status
            ) VALUES(?, ?, ?, ?, ?, 'AUTOMATIC')
            """,
            (
                (
                    clause.id,
                    clause.revision_id,
                    clause.title,
                    clause.raw_text,
                    clause.normalized_text,
                )
                for clause in materialized.clauses
            ),
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO links(id, source_id, target_id, relation_type)
            VALUES(?, ?, ?, ?)
            """,
            (
                (link.id, link.source_id, link.target_id, link.relation_type)
                for link in materialized.links
            ),
        )
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    return connection.total_changes - before


def materialize_clause_structure(connection: sqlite3.Connection) -> bool:
    """Materialize missing clauses and structural links during database build.

    This primitive intentionally does not build retrieval projections or legal
    reference links. Those operations belong to the explicit BUILDING-only
    finalization sequence after clause structure is available.
    """
    if _count(connection, "elements") == 0:
        return False
    uncovered_revisions = _uncovered_revisions(connection)
    return _insert_derived_clauses(connection, uncovered_revisions) > 0


def ensure_clause_index(connection: sqlite3.Connection) -> bool:
    """Compatibility backfill for mutable build/migration databases only.

    Clause derivation is revision-scoped: revisions that already contain explicit
    clauses are left alone, while element-only revisions are materialized. The
    semantic clause index and explicit cross-reference links are then rebuilt only
    when their derived state is missing or incomplete.
    """
    lifecycle = connection.execute(
        "SELECT value FROM snapshot_meta WHERE key = 'lifecycle_state'"
    ).fetchone()
    if lifecycle is not None and lifecycle[0] == "FINALIZED":
        raise RuntimeError("EVIDENCE_DATABASE_FINALIZED")

    changed = materialize_clause_structure(connection)

    indexable_count = _indexable_clause_count(connection)
    indexed_count = _count(connection, "clause_retrieval_records")
    fts_count = _count(connection, "clause_fts")
    if changed or indexed_count != indexable_count or fts_count != indexable_count:
        build_fts_index(connection)
    else:
        require_fresh_index(connection)

    if indexable_count > 0:
        materialize_legal_reference_links(connection)
    return changed
