"""Bounded deterministic fallback stages for clause-first legal retrieval."""

from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass
from enum import Enum

from evidence_review.retrieval.clause_resolution import (
    ClauseRetrievalHit,
    search_clause_exact,
    search_clause_phrase,
    search_clause_token_and,
    search_clause_token_prefix_and,
)
from evidence_review.retrieval.models import ChannelScore


class FallbackStage(str, Enum):
    EXACT_CLAUSE = "EXACT_CLAUSE"
    PHRASE = "PHRASE"
    TOKEN_AND = "TOKEN_AND"
    TOKEN_PREFIX = "TOKEN_PREFIX"
    APPROVED_ALIAS = "APPROVED_ALIAS"
    LEGAL_COMPOUND_DECOMPOSITION = "LEGAL_COMPOUND_DECOMPOSITION"
    HEADING_SCOPED = "HEADING_SCOPED"


@dataclass(frozen=True, slots=True)
class FallbackTrace:
    """One deterministic search attempt within the fallback ladder."""

    stage: FallbackStage
    input_query: str
    derived_query: str
    hit_count: int


@dataclass(frozen=True, slots=True)
class FallbackResult:
    """Clause hits plus the exact deterministic attempts that produced them."""

    hits: tuple[ClauseRetrievalHit, ...]
    traces: tuple[FallbackTrace, ...]
    success_stage: FallbackStage | None
    successful_query: str | None


# These are linguistic/legal-document aliases, not document-specific authorities.
# They are intentionally small and bounded; new pairs require regression coverage.
_APPROVED_TOKEN_ALIASES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("최소", "면적"), ("대지면적",)),
    (("주차장", "설치기준"), ("주차기준",)),
    (("주차기준",), ("주차장", "설치기준")),
    (("용적률",), ("기본용적률",)),
)
_GENERIC_INTENT_TOKENS = frozenset(
    {
        "기준",
        "거리",
        "요건",
        "절차",
        "검토",
        "여부",
        "가능",
        "가능여부",
        "최소",
        "완화",
        "적용",
    }
)
_MAX_DERIVED_QUERIES = 4


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    if not normalized:
        raise ValueError("query must not be empty")
    return normalized


def _ordered_unique(values: list[str], *, limit: int = _MAX_DERIVED_QUERIES) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return tuple(result)


def _replace_token_sequence(
    tokens: tuple[str, ...],
    source: tuple[str, ...],
    replacement: tuple[str, ...],
) -> tuple[str, ...] | None:
    if len(source) > len(tokens):
        return None
    for index in range(len(tokens) - len(source) + 1):
        if tokens[index : index + len(source)] == source:
            return (*tokens[:index], *replacement, *tokens[index + len(source) :])
    return None


def approved_alias_queries(query: str) -> tuple[str, ...]:
    """Derive at most four pre-approved phrase/token substitutions."""
    normalized = _normalize(query)
    tokens = tuple(normalized.split())
    values: list[str] = []
    for source, replacement in _APPROVED_TOKEN_ALIASES:
        replaced = _replace_token_sequence(tokens, source, replacement)
        if replaced is not None and replaced != tokens:
            values.append(" ".join(replaced))
    return _ordered_unique(values)


def legal_compound_queries(query: str) -> tuple[str, ...]:
    """Broaden late by dropping bounded context/intent tokens only.

    This stage never adds a token that was not present in the input query. It first
    removes generic intent tokens, then progressively drops one leading qualifier
    while retaining at least two tokens.
    """
    normalized = _normalize(query)
    tokens = tuple(normalized.split())
    values: list[str] = []

    stripped = tuple(token for token in tokens if token not in _GENERIC_INTENT_TOKENS)
    if 2 <= len(stripped) < len(tokens):
        values.append(" ".join(stripped))

    base = stripped if len(stripped) >= 2 else tokens
    for start in range(1, len(base) - 1):
        values.append(" ".join(base[start:]))

    return _ordered_unique(values)


def _row_to_heading_hit(
    row: tuple[object, ...],
    *,
    query: str,
    rank: int,
) -> ClauseRetrievalHit:
    from decimal import Decimal

    return ClauseRetrievalHit(
        clause_id=str(row[0]),
        document_id=str(row[1]),
        revision_id=str(row[2]),
        title=str(row[3]),
        chapter=None if row[4] is None else str(row[4]),
        section=None if row[5] is None else str(row[5]),
        clause_number=None if row[6] is None else str(row[6]),
        text=str(row[8]) or str(row[7]),
        channel_scores=(
            ChannelScore(
                channel="clause_heading_scoped",
                score=Decimal(1) / Decimal(rank + 1),
                detail=query,
            ),
        ),
    )


def search_clause_heading_scoped(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
) -> tuple[ClauseRetrievalHit, ...]:
    """Search title/chapter/section/clause-number fields after text fallback fails."""
    normalized = _normalize(query)
    if limit < 1:
        return ()
    tokens = tuple(normalized.split())
    if not tokens:
        return ()
    heading_expression = (
        "title || ' ' || COALESCE(chapter, '') || ' ' || "
        "COALESCE(section, '') || ' ' || COALESCE(clause_number, '')"
    )
    predicates = " AND ".join(f"({heading_expression}) LIKE ?" for _ in tokens)
    rows = connection.execute(
        f"""
        SELECT clause_id, document_id, revision_id, title, chapter, section,
               clause_number, raw_text, normalized_text
        FROM clause_retrieval_records
        WHERE {predicates}
        ORDER BY clause_id ASC
        LIMIT ?
        """,
        tuple(f"%{token}%" for token in tokens) + (limit,),
    ).fetchall()
    return tuple(
        _row_to_heading_hit(tuple(row), query=normalized, rank=index)
        for index, row in enumerate(rows)
    )


def _run_queries(
    connection: sqlite3.Connection,
    *,
    input_query: str,
    stage: FallbackStage,
    queries: tuple[str, ...],
    search: object,
    limit: int,
    traces: list[FallbackTrace],
) -> FallbackResult | None:
    if not callable(search):
        raise TypeError("search must be callable")
    for derived_query in queries:
        hits = search(connection, derived_query, limit=limit)
        traces.append(
            FallbackTrace(
                stage=stage,
                input_query=input_query,
                derived_query=derived_query,
                hit_count=len(hits),
            )
        )
        if hits:
            return FallbackResult(
                hits=hits,
                traces=tuple(traces),
                success_stage=stage,
                successful_query=derived_query,
            )
    return None


def search_clause_with_fallback(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
) -> FallbackResult:
    """Run deterministic clause retrieval stages and stop at first success."""
    normalized = _normalize(query)
    if limit < 1:
        return FallbackResult((), (), None, None)
    traces: list[FallbackTrace] = []

    strict_stages = (
        (FallbackStage.EXACT_CLAUSE, search_clause_exact),
        (FallbackStage.PHRASE, search_clause_phrase),
        (FallbackStage.TOKEN_AND, search_clause_token_and),
        (FallbackStage.TOKEN_PREFIX, search_clause_token_prefix_and),
    )
    for stage, search in strict_stages:
        result = _run_queries(
            connection,
            input_query=normalized,
            stage=stage,
            queries=(normalized,),
            search=search,
            limit=limit,
            traces=traces,
        )
        if result is not None:
            return result

    alias_queries = approved_alias_queries(normalized)
    result = _run_queries(
        connection,
        input_query=normalized,
        stage=FallbackStage.APPROVED_ALIAS,
        queries=alias_queries,
        search=search_clause_token_prefix_and,
        limit=limit,
        traces=traces,
    )
    if result is not None:
        return result

    compound_queries = legal_compound_queries(normalized)
    result = _run_queries(
        connection,
        input_query=normalized,
        stage=FallbackStage.LEGAL_COMPOUND_DECOMPOSITION,
        queries=compound_queries,
        search=search_clause_token_prefix_and,
        limit=limit,
        traces=traces,
    )
    if result is not None:
        return result

    heading_queries = _ordered_unique(
        [normalized, *alias_queries, *compound_queries]
    )
    result = _run_queries(
        connection,
        input_query=normalized,
        stage=FallbackStage.HEADING_SCOPED,
        queries=heading_queries,
        search=search_clause_heading_scoped,
        limit=limit,
        traces=traces,
    )
    if result is not None:
        return result

    return FallbackResult(
        hits=(),
        traces=tuple(traces),
        success_stage=None,
        successful_query=None,
    )
