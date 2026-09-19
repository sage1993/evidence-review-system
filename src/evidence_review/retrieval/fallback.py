"""Bounded deterministic fallback stages for clause-first legal retrieval."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
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
from evidence_review.retrieval.relevance import evaluate_issue_clause_relevance


class FallbackStage(StrEnum):
    EXACT_CLAUSE = "EXACT_CLAUSE"
    PHRASE = "PHRASE"
    TOKEN_AND = "TOKEN_AND"
    TOKEN_PREFIX = "TOKEN_PREFIX"
    FACT_DECONTAMINATED = "FACT_DECONTAMINATED"
    APPROVED_ALIAS = "APPROVED_ALIAS"
    LEGAL_COMPOUND_DECOMPOSITION = "LEGAL_COMPOUND_DECOMPOSITION"
    CORE_TOKEN_AND = "CORE_TOKEN_AND"
    HEADING_SCOPED = "HEADING_SCOPED"
    REFERENCE_EXPANSION = "REFERENCE_EXPANSION"
    LEGACY_ELEMENT = "LEGACY_ELEMENT"


class ClauseSearch(Protocol):
    def __call__(
        self,
        connection: sqlite3.Connection,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[ClauseRetrievalHit, ...]: ...


HitFilter = Callable[[ClauseRetrievalHit], bool]


@dataclass(frozen=True, slots=True)
class FallbackRelevanceDecision:
    clause_id: str
    accepted: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FallbackTrace:
    stage: FallbackStage
    input_query: str
    derived_query: str
    hit_count: int
    relevance_decisions: tuple[FallbackRelevanceDecision, ...] = ()


@dataclass(frozen=True, slots=True)
class FallbackResult:
    hits: tuple[ClauseRetrievalHit, ...]
    traces: tuple[FallbackTrace, ...]
    success_stage: FallbackStage | None
    successful_query: str | None


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
        "추가",
    }
)
_CORE_PROTECTED_SUFFIXES = (
    "계획",
    "심의",
    "협의",
    "허가",
    "인가",
    "승인",
    "신고",
    "등록",
    "위원회",
)
_NUMERIC_TOKEN = re.compile(
    r"^(?P<number>\d[\d,]*(?:\.\d+)?)"
    r"(?P<unit>m2|m²|㎡|m3|㎥|km|mm|cm|m|%|퍼센트|미터|제곱미터)?$",
    re.IGNORECASE,
)
_NUMERIC_SCAN = re.compile(
    r"(?<![\d,])(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>m2|m²|㎡|m3|㎥|km|mm|cm|m|%|퍼센트|미터|제곱미터)"
    r"(?![a-z0-9])",
    re.IGNORECASE,
)
_UNIT_KEYS = {
    "m": "length_m",
    "미터": "length_m",
    "m2": "area_m2",
    "m²": "area_m2",
    "㎡": "area_m2",
    "제곱미터": "area_m2",
    "m3": "volume_m3",
    "㎥": "volume_m3",
    "%": "percent",
    "퍼센트": "percent",
    "km": "length_km",
    "mm": "length_mm",
    "cm": "length_cm",
}
_MAX_CORE_VARIANTS = 10
_HEADING_STOP_TOKENS = frozenset(
    {
        "기준",
        "검토",
        "검색",
        "검색한다",
        "검색하는",
        "검색한다.",
        "관련",
        "무엇인가",
        "무엇인가?",
        "어떤",
        "정하는",
        "정한다",
        "조항",
        "조항을",
        "법령",
        "조례",
        "지침",
        "법령·조례·지침·기준",
        "여부",
        "적용",
        "최소",
        "최대",
        "추가",
    }
)


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(token for token in _normalize_text(value).split(" ") if token)


def _approved_alias_queries(value: str) -> tuple[str, ...]:
    tokens = _tokenize(value)
    queries: list[str] = []
    for source, replacement in _APPROVED_TOKEN_ALIASES:
        source_length = len(source)
        for start in range(len(tokens) - source_length + 1):
            if tuple(tokens[start : start + source_length]) != source:
                continue
            derived_tokens = [
                *tokens[:start],
                *replacement,
                *tokens[start + source_length :],
            ]
            derived = _normalize_text(" ".join(derived_tokens))
            if derived and derived != _normalize_text(value) and derived not in queries:
                queries.append(derived)
            break
    return tuple(queries)


def _compound_decomposition_queries(value: str) -> tuple[str, ...]:
    tokens = list(_tokenize(value))
    if len(tokens) < 2:
        return ()
    content = [token for token in tokens if token not in _GENERIC_INTENT_TOKENS]
    if len(content) < 2:
        return ()
    derived = _normalize_text(" ".join(content))
    if derived == _normalize_text(value):
        return ()
    return (derived,)


def _clean_token(value: str) -> str:
    return value.strip(".,!?;:()[]{}<>\\\"'“”‘’")


def _numeric_key_parts(number_text: str, unit_text: str) -> str | None:
    try:
        number = Decimal(number_text.replace(",", ""))
    except InvalidOperation:
        return None
    number_key = format(number.normalize(), "f")
    unit = unicodedata.normalize("NFKC", unit_text).casefold()
    unit_key = _UNIT_KEYS.get(unit, unit)
    return f"{number_key}:{unit_key}"


def _numeric_key(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    match = _NUMERIC_TOKEN.fullmatch(normalized)
    if match is None:
        return None
    return _numeric_key_parts(match.group("number"), match.group("unit") or "")


def _numeric_values(texts: Sequence[str]) -> frozenset[str]:
    values: set[str] = set()
    for text in texts:
        normalized = _normalize_text(text).casefold()
        for match in _NUMERIC_SCAN.finditer(normalized):
            key = _numeric_key_parts(match.group("number"), match.group("unit"))
            if key is not None:
                values.add(key)
        for token in normalized.split(" "):
            key = _numeric_key(_clean_token(token))
            if key is not None:
                values.add(key)
    return frozenset(values)


def _fact_decontaminated_query(
    value: str,
    fact_texts: Sequence[str],
) -> str | None:
    tokens = list(_tokenize(value))
    removable = _numeric_values(fact_texts)
    if not removable:
        return None
    kept = [
        token
        for token in tokens
        if _numeric_key(_clean_token(token)) not in removable
    ]
    if len(kept) < 2 or len(kept) == len(tokens):
        return None
    return _normalize_text(" ".join(kept))


def _protected_core_tokens(value: str) -> frozenset[str]:
    protected: set[str] = set()
    for token in _tokenize(value):
        cleaned = _clean_token(token)
        if any(cleaned.endswith(suffix) for suffix in _CORE_PROTECTED_SUFFIXES):
            protected.add(cleaned)
    return frozenset(protected)


def _protected_numeric_tokens(
    value: str,
    fact_texts: Sequence[str],
) -> frozenset[str]:
    removable = _numeric_values(fact_texts)
    protected: set[str] = set()
    for token in _tokenize(value):
        cleaned = _clean_token(token)
        key = _numeric_key(cleaned)
        if key is not None and key not in removable:
            protected.add(cleaned)
    return frozenset(protected)


def _core_token_queries(
    value: str,
    *,
    required_tokens: Iterable[str] = (),
) -> tuple[str, ...]:
    tokens = list(_tokenize(value))
    if len(tokens) <= 2:
        return ()
    required = frozenset(_clean_token(token) for token in required_tokens)
    queries: list[str] = []

    def add(candidate_tokens: Sequence[str]) -> None:
        if len(candidate_tokens) < 2 or len(queries) >= _MAX_CORE_VARIANTS:
            return
        cleaned_tokens = frozenset(_clean_token(token) for token in candidate_tokens)
        if not required.issubset(cleaned_tokens):
            return
        candidate = _normalize_text(" ".join(candidate_tokens))
        if candidate and candidate != _normalize_text(value) and candidate not in queries:
            queries.append(candidate)

    for removed in range(len(tokens)):
        add((*tokens[:removed], *tokens[removed + 1 :]))
    for width in (3, 2):
        for start in range(len(tokens) - width + 1):
            add(tokens[start : start + width])
            if len(queries) >= _MAX_CORE_VARIANTS:
                break
        if len(queries) >= _MAX_CORE_VARIANTS:
            break
    return tuple(queries)


def approved_alias_queries(value: str) -> tuple[str, ...]:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError("query must be non-empty")
    return _approved_alias_queries(normalized)


def legal_compound_queries(value: str) -> tuple[str, ...]:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError("query must be non-empty")
    return _compound_decomposition_queries(normalized)


def _heading_scoped_search(
    connection: sqlite3.Connection,
    query: str,
    *,
    required_tokens: Iterable[str] = (),
    limit: int,
) -> tuple[ClauseRetrievalHit, ...]:
    require_fresh_index(connection)
    tokens = _tokenize(query)
    if not tokens:
        return ()
    required = tuple(
        _clean_token(token) for token in required_tokens if _clean_token(token)
    )
    token_conditions: list[str] = []
    parameters: list[str] = []
    for token in tokens:
        token_conditions.append(
            "(" + " OR ".join(
                (
                    '" " || r.normalized_text || " " LIKE ?',
                    '" " || r.title || " " LIKE ?',
                    '" " || COALESCE(r.chapter, \'\') || " " LIKE ?',
                    '" " || COALESCE(r.section, \'\') || " " LIKE ?',
                    '" " || COALESCE(r.clause_number, \'\') || " " LIKE ?',
                )
            ) + ")"
        )
        parameters.extend([f"%{token}%"] * 5)
    rows = connection.execute(
        f"""
        SELECT r.clause_id, r.document_id, r.revision_id, r.title,
               r.chapter, r.section, r.clause_number, r.raw_text,
               r.normalized_text
        FROM clause_retrieval_records AS r
        WHERE {' OR '.join(token_conditions)}
        ORDER BY r.clause_id
        """,
        parameters,
    ).fetchall()
    ranked: list[tuple[int, int, str, ClauseRetrievalHit]] = []
    for row in rows:
        headings = _normalize_text(
            " ".join("" if value is None else str(value) for value in row[3:9])
        )
        if any(token not in headings for token in required):
            continue
        matched_tokens = sum(token in headings for token in tokens)
        meaningful_tokens = []
        for token in tokens:
            cleaned = _clean_token(token)
            if cleaned in _HEADING_STOP_TOKENS:
                continue
            for suffix in (
                "에서",
                "으로",
                "에게",
                "의",
                "을",
                "를",
                "은",
                "는",
                "이",
                "가",
                "에",
                "로",
                "과",
                "와",
                "도",
                "만",
            ):
                if len(cleaned) > len(suffix) + 1 and cleaned.endswith(suffix):
                    cleaned = cleaned[: -len(suffix)]
                    break
            if cleaned and cleaned not in _HEADING_STOP_TOKENS:
                meaningful_tokens.append(cleaned)
        if meaningful_tokens and not all(token in headings for token in meaningful_tokens):
            continue
        heading_matches = sum(
            token in _normalize_text(
                " ".join("" if value is None else str(value) for value in row[3:7])
            )
            for token in tokens
        )
        hit = ClauseRetrievalHit(
            clause_id=str(row[0]),
            document_id=str(row[1]),
            revision_id=str(row[2]),
            title=str(row[3]),
            chapter=None if row[4] is None else str(row[4]),
            section=None if row[5] is None else str(row[5]),
            clause_number=None if row[6] is None else str(row[6]),
            text=str(row[8] or row[7] or ""),
            channel_scores=(
                ChannelScore(
                    "clause_heading_scoped",
                    Decimal(matched_tokens * 2 + heading_matches)
                    / Decimal(max(len(tokens) * 3, 1)),
                    f"heading-token-coverage:{matched_tokens}/{len(tokens)}",
                ),
            ),
        )
        ranked.append((matched_tokens, heading_matches, hit.clause_id, hit))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    candidate_limit = max(limit * 16, 100)
    return tuple(item[3] for item in ranked[:candidate_limit])


def _accepted_hits(
    original_query: str,
    hits: Sequence[ClauseRetrievalHit],
    hit_filter: HitFilter | None,
) -> tuple[tuple[ClauseRetrievalHit, ...], tuple[FallbackRelevanceDecision, ...]]:
    accepted: list[ClauseRetrievalHit] = []
    decisions: list[FallbackRelevanceDecision] = []
    for hit in hits:
        relevance = evaluate_issue_clause_relevance(
            issue_id="QUERY",
            issue_question=original_query,
            search_request_id="QUERY",
            query_text=original_query,
            clause=hit,
        )
        accepted_by_filter = hit_filter is None or hit_filter(hit)
        is_accepted = relevance.accepted and accepted_by_filter
        reason_codes = relevance.reason_codes
        if relevance.accepted and not accepted_by_filter:
            reason_codes = ("REJECT_CALLER_FILTER",)
        decisions.append(
            FallbackRelevanceDecision(
                clause_id=hit.clause_id,
                accepted=is_accepted,
                reason_codes=reason_codes,
            )
        )
        if is_accepted:
            accepted.append(hit)
    return tuple(accepted), tuple(decisions)


def search_clause_with_fallback(
    connection: sqlite3.Connection,
    query: str,
    *,
    fact_texts: Sequence[str] = (),
    limit: int = 20,
    hit_filter: HitFilter | None = None,
    allow_heading_scoped: bool = True,
    allow_derived_fallback: bool = True,
) -> FallbackResult:
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
    decontaminated = (
        _fact_decontaminated_query(normalized, fact_texts)
        if allow_derived_fallback
        else None
    )
    if decontaminated is not None:
        attempts.append(
            (
                FallbackStage.FACT_DECONTAMINATED,
                decontaminated,
                search_clause_token_prefix_and,
            )
        )

    bases = tuple(
        dict.fromkeys(
            (normalized, decontaminated) if decontaminated is not None else (normalized,)
        )
    )
    protected_mechanisms = _protected_core_tokens(normalized)
    protected_numerics = _protected_numeric_tokens(normalized, fact_texts)
    if allow_derived_fallback:
        for base in bases:
            attempts.extend(
                (FallbackStage.APPROVED_ALIAS, derived, search_clause_token_and)
                for derived in _approved_alias_queries(base)
            )

        compound_queries: list[str] = []
        for base in bases:
            for derived in _compound_decomposition_queries(base):
                if derived in compound_queries:
                    continue
                compound_queries.append(derived)
                attempts.append(
                    (
                        FallbackStage.LEGAL_COMPOUND_DECOMPOSITION,
                        derived,
                        search_clause_token_prefix_and,
                    )
                )

        protected_tokens = protected_mechanisms | protected_numerics
        core_queries: list[str] = []
        for base in tuple(dict.fromkeys((*bases, *compound_queries))):
            for derived in _core_token_queries(base, required_tokens=protected_tokens):
                if derived in core_queries:
                    continue
                core_queries.append(derived)
                attempts.append(
                    (
                        FallbackStage.CORE_TOKEN_AND,
                        derived,
                        search_clause_token_prefix_and,
                    )
                )
                if len(core_queries) >= _MAX_CORE_VARIANTS:
                    break
            if len(core_queries) >= _MAX_CORE_VARIANTS:
                break

    traces: list[FallbackTrace] = []
    seen: set[tuple[FallbackStage, str]] = set()
    for stage, derived_query, search in attempts:
        key = (stage, derived_query)
        if key in seen:
            continue
        seen.add(key)
        raw_hits = search(connection, derived_query, limit=limit)
        hits, decisions = _accepted_hits(normalized, raw_hits, hit_filter)
        traces.append(
            FallbackTrace(
                stage=stage,
                input_query=normalized,
                derived_query=derived_query,
                hit_count=len(hits),
                relevance_decisions=decisions,
            )
        )
        if hits:
            return FallbackResult(
                hits=hits,
                traces=tuple(traces),
                success_stage=stage,
                successful_query=derived_query,
            )

    heading_query = decontaminated or normalized
    raw_heading_hits = (
        ()
        if protected_numerics or not allow_heading_scoped
        else _heading_scoped_search(
            connection,
            heading_query,
            required_tokens=protected_mechanisms,
            limit=limit,
        )
    )
    heading_hits, heading_decisions = _accepted_hits(
        normalized,
        raw_heading_hits,
        hit_filter,
    )
    heading_hits = heading_hits[:limit]
    traces.append(
        FallbackTrace(
            stage=FallbackStage.HEADING_SCOPED,
            input_query=normalized,
            derived_query=heading_query,
            hit_count=len(heading_hits),
            relevance_decisions=heading_decisions,
        )
    )
    if heading_hits:
        return FallbackResult(
            hits=heading_hits,
            traces=tuple(traces),
            success_stage=FallbackStage.HEADING_SCOPED,
            successful_query=heading_query,
        )
    return FallbackResult(
        hits=(),
        traces=tuple(traces),
        success_stage=None,
        successful_query=None,
    )
