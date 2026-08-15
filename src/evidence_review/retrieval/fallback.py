"""Bounded deterministic fallback stages for clause-first legal retrieval."""

from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol

from evidence_review.retrieval.clause_resolution import (
    ClauseRetrievalHit,
    search_clause_exact,
    search_clause_phrase,
    search_clause_token_and,
    search_clause_token_prefix_and,
)
from evidence_review.retrieval.index import require_fresh_index
from evidence_review.retrieval.models import ChannelScore


class FallbackStage(str, Enum):
    EXACT_CLAUSE = "EXACT_CLAUSE"
    PHRASE = "PHRASE"
    TOKEN_AND = "TOKEN_AND"
    TOKEN_PREFIX = "TOKEN_PREFIX"
    APPROVED_ALIAS = "APPROVED_ALIAS"
    LEGAL_COMPOUND_DECOMPOSITION = "LEGAL_COMPOUND_DECOMPOSITION"
    HEADING_SCOPED = "HEADING_SCOPED"
    REFERENCE_EXPANSION = "REFERENCE_EXPANSION"


class ClauseSearch(Protocol):
    def __call__(
        self,
        connection: sqlite3.Connection,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[ClauseRetrievalHit, ...]: ...


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


# Linguistic/legal-document aliases only. Do not add document-specific authorities.
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
        "최대",
        "적용",
        "완화",
    }
)


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(token for token in _normalize_text(value).split(" ") if token)


def _approved_alias_queries(value: str) -> tuple[str, ...]:
    tokens = _tokenize(value)
    queries: list[str] = []
    token_set = set(tokens)
    for source, replacement in _APPROVED_TOKEN_ALIASES:
        if not set(source).issubset(token_set):
            continue
        remaining = [token for token in tokens if token not in source]
        derived = _normalize_text(" ".join((*remaining, *replacement)))
        if derived and derived != _normalize_text(value) and derived not in queries:
            queries.append(derived)
    return tuple(queries)


def _compound_decomposition_queries(value: str) -> tuple[str, ...]:
    tokens = list(_tokenize(value))
    if len(tokens) < 2:
        return ()
    content = [token for token in tokens if token not in _GENERIC_INTENT_TOKENS]
    if not content:
        return ()
    derived = _normalize_text(" ".join(content))
    if derived == _normalize_text(value):
        return ()
    return (derived,)


def _heading_scoped_search(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int,
) -> tuple[ClauseRetrievalHit, ...]:
    require_fresh_index(connection)
    tokens = _tokenize(query)
    if not tokens:
        return ()
    rows = connection.execute(
        """
        SELECT r.clause_id, r.document_id, r.revision_id, r.title,
               r.chapter, r.section, r.clause_number, r.normalized_text,
               r.source_element_ids_json
        FROM clause_retrieval_records AS r
        WHERE " " || r.normalized_text || " " LIKE ?
           OR " " || r.title || " " LIKE ?
           OR " " || COALESCE(r.chapter, '') || " " LIKE ?
           OR " " || COALESCE(r.section, '') || " " LIKE ?
        ORDER BY r.clause_id
        LIMIT ?
        """,
        (
            f"%{tokens[0]}%",
            f"%{tokens[0]}%",
            f"%{tokens[0]}%",
            f"%{tokens[0]}%",
            limit,
        ),
    ).fetchall()
    hits: list[ClauseRetrievalHit] = []
    for index, row in enumerate(rows):
        score = Decimal(limit - index) / Decimal(max(limit, 1))
        hits.append(
            ClauseRetrievalHit.from_row(
                row,
                channel=ChannelScore(
                    "clause_heading_scoped",
                    score,
                    f"heading-token:{tokens[0]}",
                ),
            )
        )
    return tuple(hits)


def search_clause_with_fallback(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
) -> FallbackResult:
    """Search clause records through a deterministic bounded fallback ladder."""
    normalized = _normalize_text(query)
    if not normalized:
        raise ValueError("query must be non-empty")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    attempts: list[tuple[FallbackStage, str, ClauseSearch]] = [
        (FallbackStage.EXACT_CLAUSE, normalized, search_clause_exact),
        (FallbackStage.PHRASE, normalized, search_clause_phrase),
        (FallbackStage.TOKEN_AND, normalized, search_clause_token_and),
        (FallbackStage.TOKEN_PREFIX, normalized, search_clause_token_prefix_and),
    ]
    attempts.extend(
        (FallbackStage.APPROVED_ALIAS, derived, search_clause_token_and)
        for derived in _approved_alias_queries(normalized)
    )
    attempts.extend(
        (FallbackStage.LEGAL_COMPOUND_DECOMPOSITION, derived, search_clause_token_and)
        for derived in _compound_decomposition_queries(normalized)
    )

    traces: list[FallbackTrace] = []
    for stage, derived_query, search in attempts:
        hits = search(connection, derived_query, limit=limit)
        traces.append(
            FallbackTrace(
                stage=stage,
                input_query=normalized,
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

    heading_hits = _heading_scoped_search(connection, normalized, limit=limit)
    traces.append(
        FallbackTrace(
            stage=FallbackStage.HEADING_SCOPED,
            input_query=normalized,
            derived_query=normalized,
            hit_count=len(heading_hits),
        )
    )
    if heading_hits:
        return FallbackResult(
            hits=heading_hits,
            traces=tuple(traces),
            success_stage=FallbackStage.HEADING_SCOPED,
            successful_query=normalized,
        )
    return FallbackResult(
        hits=(),
        traces=tuple(traces),
        success_stage=None,
        successful_query=None,
    )
