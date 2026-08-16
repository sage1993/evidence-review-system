"""Backfill deterministic clause artifacts for element-only schema-v4 workspaces."""

from __future__ import annotations

import sqlite3

from evidence_review.evidence.clause_materialization import derive_legal_clauses
from evidence_review.retrieval.index import build_fts_index, require_fresh_index


def _source_elements(connection: sqlite3.Connection) -> tuple[dict[str, object], ...]:
    rows = connection.execute(
        """
        SELECT e.id, p.revision_id, p.page_number, e.parser_order,
               e.raw_text, e.normalized_text
        FROM elements e
        JOIN pages p ON p.id = e.page_id
        ORDER BY p.revision_id, p.page_number, e.parser_order, e.id
        """
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


def _count(connection: sqlite3.Connection, table: str) -> int:
    allowed = {
        "elements",
        "clauses",
        "clause_retrieval_records",
        "clause_fts",
    }
    if table not in allowed:
        raise ValueError(f"unsupported table: {table}")
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return 0 if row is None else int(row[0])


def _insert_derived_clauses(connection: sqlite3.Connection) -> int:
    materialized = derive_legal_clauses(_source_elements(connection))
    if not materialized.clauses:
        return 0

    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.executemany(
            """
            INSERT INTO clauses(
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
    return len(materialized.clauses)


def ensure_clause_index(connection: sqlite3.Connection) -> bool:
    """Backfill missing derived clauses/indexes without changing parser evidence.

    Returns ``True`` only when new clause records were derived. Existing explicit
    clauses are never replaced. The current schema-v4 index trigger is reused to
    publish ``clause_retrieval_records``, ``clause_fts`` and citation links.
    """
    if _count(connection, "elements") == 0:
        require_fresh_index(connection)
        return False

    changed = False
    if _count(connection, "clauses") == 0:
        changed = _insert_derived_clauses(connection) > 0

    clause_count = _count(connection, "clauses")
    indexed_count = _count(connection, "clause_retrieval_records")
    fts_count = _count(connection, "clause_fts")
    if changed or (clause_count > 0 and (indexed_count == 0 or fts_count == 0)):
        build_fts_index(connection)
    else:
        require_fresh_index(connection)
    return changed
