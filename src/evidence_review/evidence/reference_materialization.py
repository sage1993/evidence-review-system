"""Materialize bounded evidence-level links for explicit legal references."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata

from evidence_review.evidence.legal_references import LegalReference, extract_legal_references

_DERIVED_REFERENCE_RELATIONS = (
    "rule_source",
    "source_not_ingested",
    "reference_target_missing",
)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24].upper()
    return f"{prefix}-{digest}"


def _canonical_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^0-9a-z가-힣]", "", normalized)


def _document_id(connection: sqlite3.Connection, authority_title: str) -> str | None:
    wanted = _canonical_title(authority_title)
    rows = connection.execute("SELECT id, title FROM documents ORDER BY id").fetchall()
    exact = [str(row[0]) for row in rows if _canonical_title(str(row[1])) == wanted]
    if len(exact) == 1:
        return exact[0]
    contained = [
        str(row[0])
        for row in rows
        if wanted
        and (
            wanted in _canonical_title(str(row[1]))
            or _canonical_title(str(row[1])) in wanted
        )
    ]
    return contained[0] if len(contained) == 1 else None


def _target_evidence_ids(
    connection: sqlite3.Connection,
    document_id: str,
    reference: LegalReference,
) -> tuple[str, ...]:
    if reference.annex is not None:
        compact_annex = reference.annex.replace(" ", "")
        token = f"%{compact_annex}%"
        rows = connection.execute(
            """
            SELECT evidence_id
            FROM retrieval_records
            WHERE document_id = ?
              AND (
                    REPLACE(normalized_text, ' ', '') LIKE ?
                    OR REPLACE(title, ' ', '') LIKE ?
                  )
            ORDER BY evidence_id
            LIMIT 5
            """,
            (document_id, token, token),
        ).fetchall()
        if rows:
            return tuple(str(row[0]) for row in rows)

    if reference.article is not None:
        article = f"%{reference.article}%"
        parameters: list[object] = [document_id, article, article, article]
        paragraph_sql = ""
        if reference.paragraph is not None:
            paragraph = f"%{reference.paragraph}%"
            paragraph_sql = (
                " AND (cr.title LIKE ? OR cr.raw_text LIKE ? "
                "OR cr.normalized_text LIKE ?)"
            )
            parameters.extend((paragraph, paragraph, paragraph))
        rows = connection.execute(
            f"""
            SELECT DISTINCT cel.evidence_id
            FROM clause_retrieval_records cr
            JOIN clause_evidence_links cel ON cel.clause_id = cr.clause_id
            WHERE cr.document_id = ?
              AND (
                    cr.title LIKE ?
                    OR cr.raw_text LIKE ?
                    OR cr.normalized_text LIKE ?
                  )
              {paragraph_sql}
            ORDER BY cel.evidence_id
            LIMIT 5
            """,
            tuple(parameters),
        ).fetchall()
        if rows:
            return tuple(str(row[0]) for row in rows)

    return ()


def _source_clauses(connection: sqlite3.Connection) -> tuple[tuple[str, str, str], ...]:
    rows = connection.execute(
        """
        SELECT c.id, COALESCE(c.normalized_text, c.raw_text, ''), cel.evidence_id
        FROM clauses c
        JOIN clause_evidence_links cel
          ON cel.clause_id = c.id AND cel.relation_type = 'source_element'
        WHERE COALESCE(c.normalized_text, c.raw_text, '') <> ''
        ORDER BY c.id, cel.evidence_id
        """
    ).fetchall()
    return tuple((str(row[0]), str(row[1]), str(row[2])) for row in rows)


def _delete_derived_reference_links(connection: sqlite3.Connection) -> None:
    placeholders = ", ".join("?" for _ in _DERIVED_REFERENCE_RELATIONS)
    connection.execute(
        f"""
        DELETE FROM links
        WHERE id GLOB 'AUTO-REF-LINK-*'
          AND relation_type IN ({placeholders})
        """,
        _DERIVED_REFERENCE_RELATIONS,
    )


def materialize_legal_reference_links(connection: sqlite3.Connection) -> int:
    """Rebuild explicit legal citation links from the current ingested source set."""
    links: dict[tuple[str, str, str], tuple[str, str, str, str]] = {}
    for clause_id, text, source_evidence_id in _source_clauses(connection):
        for reference in extract_legal_references(text):
            document_id = _document_id(connection, reference.authority_title)
            reference_key = "|".join(
                value or ""
                for value in (
                    reference.authority_title,
                    reference.article,
                    reference.paragraph,
                    reference.annex,
                )
            )
            if document_id is None:
                target_id = _stable_id("MISSING-SOURCE", reference_key)
                relation_type = "source_not_ingested"
                targets = (target_id,)
            else:
                resolved = _target_evidence_ids(connection, document_id, reference)
                if resolved:
                    relation_type = "rule_source"
                    targets = resolved
                else:
                    relation_type = "reference_target_missing"
                    targets = (
                        _stable_id("MISSING-REFERENCE", document_id, reference_key),
                    )

            for target_id in targets:
                key = (source_evidence_id, target_id, relation_type)
                links[key] = (
                    _stable_id(
                        "AUTO-REF-LINK",
                        clause_id,
                        source_evidence_id,
                        target_id,
                        relation_type,
                    ),
                    source_evidence_id,
                    target_id,
                    relation_type,
                )

    before = connection.total_changes
    connection.execute("BEGIN IMMEDIATE")
    try:
        _delete_derived_reference_links(connection)
        if links:
            connection.executemany(
                """
                INSERT INTO links(id, source_id, target_id, relation_type)
                VALUES(?, ?, ?, ?)
                """,
                tuple(links.values()),
            )
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    return connection.total_changes - before
