"""Clause-first lexical retrieval and fail-closed citation materialization."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from evidence_review.retrieval.index import load_indexed_hit, require_fresh_index
from evidence_review.retrieval.models import ChannelScore, RetrievalHit


@dataclass(frozen=True, slots=True)
class ClauseRetrievalHit:
    """Semantic clause hit before page/bbox citation materialization."""

    clause_id: str
    document_id: str
    revision_id: str
    title: str
    text: str
    chapter: str | None = None
    section: str | None = None
    clause_number: str | None = None
    channel_scores: tuple[ChannelScore, ...] = ()

    @property
    def score(self) -> Decimal:
        """Return the strongest deterministic channel score for this clause."""
        return max(
            (channel.score for channel in self.channel_scores),
            default=Decimal("0"),
        )


def _normalized_query(query: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(query.split()))
    if not normalized:
        raise ValueError("query must not be empty")
    return normalized


def _quoted_literal(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _phrase_match_expression(query: str) -> str:
    return _quoted_literal(_normalized_query(query))


def _token_and_match_expression(query: str) -> str:
    return " AND ".join(
        _quoted_literal(token) for token in _normalized_query(query).split(" ")
    )


def _token_prefix_and_match_expression(query: str) -> str:
    return " AND ".join(
        f"{_quoted_literal(token)}*"
        for token in _normalized_query(query).split(" ")
    )


def _row_to_clause_hit(
    row: sqlite3.Row | tuple[object, ...],
    rank_index: int,
    query: str,
    channel: str,
) -> ClauseRetrievalHit:
    score = Decimal(1) / Decimal(rank_index + 1)
    raw_text = "" if row[7] is None else str(row[7])
    normalized_text = "" if row[8] is None else str(row[8])
    return ClauseRetrievalHit(
        clause_id=str(row[0]),
        document_id=str(row[1]),
        revision_id=str(row[2]),
        title=str(row[3]),
        chapter=None if row[4] is None else str(row[4]),
        section=None if row[5] is None else str(row[5]),
        clause_number=None if row[6] is None else str(row[6]),
        text=normalized_text or raw_text,
        channel_scores=(ChannelScore(channel=channel, score=score, detail=query),),
    )


def _search_clause_fts(
    connection: sqlite3.Connection,
    query: str,
    *,
    match_expression: str,
    channel: str,
    limit: int,
) -> tuple[ClauseRetrievalHit, ...]:
    require_fresh_index(connection)
    if limit < 1:
        return ()
    rows = connection.execute(
        """
        SELECT cr.clause_id, cr.document_id, cr.revision_id, cr.title,
               cr.chapter, cr.section, cr.clause_number, cr.raw_text,
               cr.normalized_text, bm25(clause_fts) AS bm25_rank
        FROM clause_fts
        JOIN clause_retrieval_records cr
          ON cr.clause_id = clause_fts.clause_id
        WHERE clause_fts MATCH ?
        ORDER BY bm25_rank ASC, cr.clause_id ASC
        LIMIT ?
        """,
        (match_expression, limit),
    ).fetchall()
    return tuple(
        _row_to_clause_hit(row, index, query, channel)
        for index, row in enumerate(rows)
    )


def search_clause_exact(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[ClauseRetrievalHit, ...]:
    """Return exact canonical clause id/title/number/text matches."""
    require_fresh_index(connection)
    normalized = _normalized_query(query)
    if limit < 1:
        return ()
    rows = connection.execute(
        """
        SELECT clause_id, document_id, revision_id, title, chapter, section,
               clause_number, raw_text, normalized_text
        FROM clause_retrieval_records
        WHERE clause_id = ?
           OR title = ?
           OR clause_number = ?
           OR normalized_text = ?
        ORDER BY
            CASE
                WHEN clause_id = ? THEN 0
                WHEN clause_number = ? THEN 1
                WHEN title = ? THEN 2
                ELSE 3
            END,
            clause_id ASC
        LIMIT ?
        """,
        (
            normalized,
            normalized,
            normalized,
            normalized,
            normalized,
            normalized,
            normalized,
            limit,
        ),
    ).fetchall()
    return tuple(
        _row_to_clause_hit(row, index, normalized, "clause_exact")
        for index, row in enumerate(rows)
    )


def search_clause_phrase(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[ClauseRetrievalHit, ...]:
    """Return exact-phrase clause hits from the semantic clause index."""
    return _search_clause_fts(
        connection,
        query,
        match_expression=_phrase_match_expression(query),
        channel="clause_phrase",
        limit=limit,
    )


def search_clause_token_and(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[ClauseRetrievalHit, ...]:
    """Return clause hits requiring every whitespace-delimited query token."""
    return _search_clause_fts(
        connection,
        query,
        match_expression=_token_and_match_expression(query),
        channel="clause_token_and",
        limit=limit,
    )


def search_clause_token_prefix_and(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 20,
) -> tuple[ClauseRetrievalHit, ...]:
    """Return suffix-tolerant clause hits requiring every token prefix."""
    return _search_clause_fts(
        connection,
        query,
        match_expression=_token_prefix_and_match_expression(query),
        channel="clause_token_prefix_and",
        limit=limit,
    )


_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣%㎡²]+")


def _normalized_locality_text(value: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(value.split())).casefold()


def _query_phrases(clause_hit: ClauseRetrievalHit) -> tuple[str, ...]:
    phrases: list[str] = []
    for channel in clause_hit.channel_scores:
        detail = channel.detail.strip()
        if not detail or detail.startswith("clause:"):
            continue
        if detail.startswith("heading-token:"):
            detail = detail.split(":", 1)[1]
        normalized = _normalized_locality_text(detail)
        if normalized and normalized not in phrases:
            phrases.append(normalized)
    return tuple(phrases)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(_normalized_locality_text(value)))


def _locality_sort_key(
    row: sqlite3.Row | tuple[object, ...],
    phrases: tuple[str, ...],
) -> tuple[int, int, int, int, str]:
    evidence_id = str(row[0])
    relation_type = str(row[1])
    raw_text = "" if row[2] is None else str(row[2])
    normalized_text = "" if row[3] is None else str(row[3])
    parser_order = 2**31 - 1 if row[4] is None else int(row[4])
    searchable = _normalized_locality_text(normalized_text or raw_text)
    phrase_match = any(phrase in searchable for phrase in phrases)
    query_tokens = frozenset(token for phrase in phrases for token in _tokens(phrase))
    overlap = len(query_tokens & _tokens(searchable))
    relation_rank = 0 if relation_type == "source_element" else 1
    return (
        0 if phrase_match else 1,
        -overlap,
        relation_rank,
        parser_order,
        evidence_id,
    )


def resolve_clause_to_evidence(
    connection: sqlite3.Connection,
    clause_hit: ClauseRetrievalHit,
    *,
    max_source_elements: int = 5,
) -> tuple[RetrievalHit, ...]:
    """Materialize verified same-revision evidence nearest to the semantic match.

    A semantic clause with no verified page/bbox source remains a valid retrieval
    hit, but this function returns no evidence rather than inventing a citation.
    """
    require_fresh_index(connection)
    if max_source_elements < 1:
        return ()
    rows = connection.execute(
        """
        SELECT cel.evidence_id, cel.relation_type, rr.raw_text,
               rr.normalized_text, e.parser_order
        FROM clause_evidence_links cel
        JOIN retrieval_records rr ON rr.evidence_id = cel.evidence_id
        LEFT JOIN elements e ON e.id = cel.evidence_id
        WHERE cel.clause_id = ?
          AND rr.revision_id = ?
          AND rr.bbox_json <> 'null'
        """,
        (clause_hit.clause_id, clause_hit.revision_id),
    ).fetchall()
    phrases = _query_phrases(clause_hit)
    ordered_rows = sorted(rows, key=lambda row: _locality_sort_key(row, phrases))[
        :max_source_elements
    ]
    semantic_score = clause_hit.score or Decimal("1")
    hits: list[RetrievalHit] = []
    for evidence_id, relation_type, _raw_text, _normalized_text, _parser_order in ordered_rows:
        hit = load_indexed_hit(
            connection,
            str(evidence_id),
            ChannelScore(
                channel="clause_citation",
                score=semantic_score,
                detail=(
                    f"clause:{clause_hit.clause_id};"
                    f"relation:{relation_type}"
                ),
            ),
        )
        if hit is None or hit.revision_id != clause_hit.revision_id or hit.bbox is None:
            continue
        hits.append(hit)
    return tuple(hits)
