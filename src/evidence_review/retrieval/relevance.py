"""Deterministic subject/section relevance gates for legal clause retrieval."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit

_SUBJECT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("역세권", "간선도로변"),
)
_REQUIRED_ANCHOR_RULES: tuple[
    tuple[tuple[str, ...], tuple[tuple[str, ...], ...]], ...
] = (
    (("최소", "면적"), (("최소", "면적"), ("최소면적",), ("대지면적",))),
    (("산업부지", "확보비율"), (("산업부지", "확보비율"),)),
)
_REQUIRED_INTENT_RULES: tuple[
    tuple[tuple[str, ...], tuple[tuple[str, ...], ...]], ...
] = (
    (
        ("공공기여", "산정"),
        (
            ("공공기여", "산정"),
            ("공공기여", "비율"),
            ("공공기여", "면적"),
            ("공공기여", "가격"),
            ("공공기여", "부담"),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class RelevanceDecision:
    """One explainable deterministic relevance decision."""

    issue_id: str
    search_request_id: str
    clause_id: str
    accepted: bool
    reason_codes: tuple[str, ...]


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(value.split())).casefold()


def _contains_all(text: str, anchors: tuple[str, ...]) -> bool:
    return all(_normalize(anchor) in text for anchor in anchors)


def _searchable_clause_text(clause: ClauseRetrievalHit) -> str:
    return _normalize(
        " ".join(
            value
            for value in (
                clause.title,
                clause.chapter or "",
                clause.section or "",
                clause.clause_number or "",
                clause.text,
            )
            if value
        )
    )


def _required_anchor_missing(query: str, candidate: str) -> bool:
    for trigger, alternatives in _REQUIRED_ANCHOR_RULES:
        if not _contains_all(query, trigger):
            continue
        if not any(_contains_all(candidate, alternative) for alternative in alternatives):
            return True
    return False


def _required_intent_missing(query: str, candidate: str) -> bool:
    for trigger, alternatives in _REQUIRED_INTENT_RULES:
        if not _contains_all(query, trigger):
            continue
        if not any(_contains_all(candidate, alternative) for alternative in alternatives):
            return True
    return False


def _subject_conflict(query: str, candidate: str) -> bool:
    """Reject only an explicit sibling subject, not an omitted umbrella label.

    Legal source text often states the concrete criterion (for example,
    ``승강장 경계로부터 250미터``) without repeating its parent label
    ``역세권``. Absence of the requested label therefore is not itself a
    conflict. A clause that explicitly names a mutually exclusive sibling such
    as ``간선도로변`` is a deterministic conflict.
    """
    for group in _SUBJECT_GROUPS:
        requested = tuple(anchor for anchor in group if _normalize(anchor) in query)
        if not requested:
            continue
        present = tuple(anchor for anchor in group if _normalize(anchor) in candidate)
        if any(anchor in present for anchor in requested):
            continue
        if present:
            return True
    return False


def evaluate_issue_clause_relevance(
    *,
    issue_id: str,
    issue_question: str,
    search_request_id: str,
    query_text: str,
    clause: ClauseRetrievalHit,
) -> RelevanceDecision:
    """Reject only deterministic subject conflicts or missing strong anchors."""
    issue_query = _normalize(f"{issue_question} {query_text}")
    request_query = _normalize(query_text)
    candidate = _searchable_clause_text(clause)
    reasons: list[str] = []

    if _subject_conflict(issue_query, candidate):
        return RelevanceDecision(
            issue_id=issue_id,
            search_request_id=search_request_id,
            clause_id=clause.clause_id,
            accepted=False,
            reason_codes=("REJECT_SUBJECT_CONFLICT",),
        )
    if _required_anchor_missing(request_query, candidate):
        return RelevanceDecision(
            issue_id=issue_id,
            search_request_id=search_request_id,
            clause_id=clause.clause_id,
            accepted=False,
            reason_codes=("REJECT_REQUIRED_ANCHOR_MISSING",),
        )
    if _required_intent_missing(request_query, candidate):
        return RelevanceDecision(
            issue_id=issue_id,
            search_request_id=search_request_id,
            clause_id=clause.clause_id,
            accepted=False,
            reason_codes=("RETRIEVAL_RELEVANCE_INSUFFICIENT",),
        )

    if any(
        _normalize(anchor) in issue_query and _normalize(anchor) in candidate
        for group in _SUBJECT_GROUPS
        for anchor in group
    ):
        reasons.append("ACCEPT_SUBJECT_MATCH")
    if clause.title and _normalize(clause.title) in issue_query:
        reasons.append("ACCEPT_SECTION_MATCH")
    if not reasons:
        reasons.append("ACCEPT_NO_DETERMINISTIC_CONFLICT")
    return RelevanceDecision(
        issue_id=issue_id,
        search_request_id=search_request_id,
        clause_id=clause.clause_id,
        accepted=True,
        reason_codes=tuple(reasons),
    )


def query_clause_is_relevant(query_text: str, clause: ClauseRetrievalHit) -> bool:
    """Fallback-safe relevance predicate when no explicit issue object is available."""
    return evaluate_issue_clause_relevance(
        issue_id="QUERY",
        issue_question=query_text,
        search_request_id="QUERY",
        query_text=query_text,
        clause=clause,
    ).accepted
