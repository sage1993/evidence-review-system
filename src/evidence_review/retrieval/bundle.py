"""Hybrid retrieval request execution and evidence-bundle export."""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

from evidence_review.retrieval.fusion import fuse_hits, fusion_document
from evidence_review.retrieval.graph import traverse_relations
from evidence_review.retrieval.index import (
    load_adjacent_element_hits,
    require_fresh_index,
    search_fts_literal,
    search_fts_phrase,
    search_fts_token_and,
)
from evidence_review.retrieval.korean_variants import (
    derive_korean_compound_variants,
    derive_korean_query_variants,
)
from evidence_review.retrieval.models import (
    ChannelScore,
    CitationUnavailableError,
    RetrievalHit,
    RetrievalMatch,
    RetrievalOrigin,
)
from evidence_review.retrieval.query import NormalizedQuery, QueryTerm, normalize_query
from evidence_review.retrieval.structured import retrieve_clause_ids, retrieve_structured

_GROUPED_CONTEXT_CHANNELS = frozenset(
    {"fts_entity", "fts_numeric", "fts_concept", "fts_korean_compound"}
)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _strings(value: object, field: str) -> tuple[str, ...]:
    items = _sequence(value, field)
    result: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field}[{index}] must be a non-empty string")
        result.append(item)
    return tuple(result)


def _synonyms(value: object) -> dict[str, tuple[str, ...]]:
    payload = _mapping(value, "synonym_manifest")
    result: dict[str, tuple[str, ...]] = {}
    for key, items in payload.items():
        if not key:
            raise ValueError("synonym manifest keys must not be empty")
        result[key] = _strings(items, f"synonym_manifest.{key}")
    return result


def _expansions(value: object) -> tuple[Mapping[str, object], ...]:
    items = _sequence(value, "expansions")
    return tuple(_mapping(item, f"expansions[{index}]") for index, item in enumerate(items))


def _normalize_request(
    payload: object,
) -> tuple[
    NormalizedQuery,
    Mapping[str, object],
    tuple[str, ...],
    tuple[str, ...],
    int,
    int,
]:
    request = _mapping(payload, "request")
    allowed = {
        "question",
        "expansions",
        "synonym_manifest",
        "filters",
        "clause_ids",
        "seed_ids",
        "graph_depth",
        "limit",
    }
    unknown = sorted(set(request) - allowed)
    if unknown:
        raise ValueError(f"request has unknown fields: {', '.join(unknown)}")
    question = request.get("question")
    if not isinstance(question, str):
        raise ValueError("question must be a string")
    normalized = normalize_query(
        question,
        _expansions(request.get("expansions", [])),
        _synonyms(request.get("synonym_manifest", {})),
    )
    filters = _mapping(request.get("filters", {}), "filters")
    clause_ids = _strings(request.get("clause_ids", []), "clause_ids")
    seed_ids = _strings(request.get("seed_ids", []), "seed_ids")
    graph_depth = request.get("graph_depth", 1)
    limit = request.get("limit", 20)
    if isinstance(graph_depth, bool) or not isinstance(graph_depth, int):
        raise ValueError("graph_depth must be an integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    return normalized, filters, clause_ids, seed_ids, graph_depth, limit


def _trace_hits(
    hits: tuple[RetrievalHit, ...],
    *,
    origin: str,
    term: str,
    search_request_ids: tuple[str, ...] = (),
    issue_ids: tuple[str, ...] = (),
) -> tuple[RetrievalHit, ...]:
    traced: list[RetrievalHit] = []
    for hit in hits:
        item = replace(
            hit,
            channel_scores=(
                ChannelScore(
                    hit.channel_scores[0].channel,
                    hit.channel_scores[0].score,
                    f"{origin}:{term}",
                ),
            ),
        )
        for search_request_id in search_request_ids:
            item = item.with_match(
                RetrievalMatch(
                    search_request_id=search_request_id,
                    issue_ids=issue_ids,
                    query_text=term,
                    origin=cast(RetrievalOrigin, origin),
                )
            )
        traced.append(item)
    return tuple(traced)


def _origin_hits(
    connection: sqlite3.Connection,
    query: NormalizedQuery,
    limit: int,
) -> tuple[tuple[RetrievalHit, ...], ...]:
    channels: list[tuple[RetrievalHit, ...]] = []
    for term in query.terms:
        phrase_hits = search_fts_phrase(connection, term.text, limit)
        token_hits = search_fts_token_and(connection, term.text, limit)
        channels.append(
            _trace_hits(
                phrase_hits,
                origin=term.origin,
                term=term.text,
                search_request_ids=term.search_request_ids,
                issue_ids=term.issue_ids,
            )
        )
        channels.append(
            _trace_hits(
                token_hits,
                origin=term.origin,
                term=term.text,
                search_request_ids=term.search_request_ids,
                issue_ids=term.issue_ids,
            )
        )
    return tuple(channels)


def _compound_variant_hits(
    connection: sqlite3.Connection,
    primary: str,
    limit: int,
) -> tuple[tuple[RetrievalHit, ...], ...]:
    channels: list[tuple[RetrievalHit, ...]] = []
    for term in derive_korean_compound_variants(primary):
        hits = search_fts_literal(
            connection,
            term,
            channel="fts_korean_compound",
            limit=limit,
        )
        channels.append(
            _trace_hits(
                hits,
                origin="derived:korean_compound",
                term=term,
            )
        )
    return tuple(channels)


def _derived_variant_hits(
    connection: sqlite3.Connection,
    primary: str,
    limit: int,
) -> tuple[tuple[RetrievalHit, ...], ...]:
    variants = derive_korean_query_variants(primary)
    channels: list[tuple[RetrievalHit, ...]] = []
    derived_groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("entity", variants.entity),
        ("numeric", variants.numeric),
        ("concept", variants.concept),
    )
    for group, terms in derived_groups:
        for term in terms:
            hits = search_fts_literal(
                connection,
                term,
                channel=f"fts_{group}",
                limit=limit,
            )
            channels.append(
                _trace_hits(
                    hits,
                    origin=f"derived:{group}",
                    term=term,
                )
            )
    return tuple(channels)


def _is_grouped_context_seed(hit: RetrievalHit) -> bool:
    return any(score.channel in _GROUPED_CONTEXT_CHANNELS for score in hit.channel_scores)


def _citation_document(hit: RetrievalHit) -> dict[str, object]:
    citation = hit.citation()
    return {
        "citation_id": citation.citation_id,
        "document_id": citation.document_id,
        "revision_id": citation.revision_id,
        "page_number": citation.page_number,
        "evidence_id": citation.evidence_id,
        "bbox": [
            citation.bbox.left,
            citation.bbox.bottom,
            citation.bbox.right,
            citation.bbox.top,
        ],
        "source_hash": citation.source_hash,
    }


def _query_term_document(term: QueryTerm) -> dict[str, object]:
    document: dict[str, object] = {"text": term.text, "origin": term.origin}
    if term.search_request_ids:
        document["search_request_ids"] = list(term.search_request_ids)
    if term.issue_ids:
        document["issue_ids"] = list(term.issue_ids)
    return document


def build_evidence_bundle(
    connection: sqlite3.Connection,
    request_payload: object,
) -> dict[str, object]:
    """Execute all deterministic retrieval channels and return a bundle."""
    snapshot_hash = require_fresh_index(connection)
    query, filters, clause_ids, seed_ids, graph_depth, limit = _normalize_request(request_payload)
    compound_variants = derive_korean_compound_variants(query.primary)
    variants = derive_korean_query_variants(query.primary)
    attempted_terms: list[dict[str, str]] = []
    attempted_seen: set[tuple[str, str]] = set()
    candidate: tuple[str, str]
    for query_term in query.terms:
        candidate = (query_term.text, query_term.origin)
        if candidate not in attempted_seen:
            attempted_seen.add(candidate)
            attempted_terms.append({"text": query_term.text, "origin": query_term.origin})
    for compound_term in compound_variants:
        candidate = (compound_term, "derived:korean_compound")
        if candidate not in attempted_seen:
            attempted_seen.add(candidate)
            attempted_terms.append({"text": compound_term, "origin": "derived:korean_compound"})
    derived_groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("entity", variants.entity),
        ("numeric", variants.numeric),
        ("concept", variants.concept),
    )
    for group, derived_terms in derived_groups:
        for derived_term in derived_terms:
            candidate = (derived_term, f"derived:{group}")
            if candidate not in attempted_seen:
                attempted_seen.add(candidate)
                attempted_terms.append({"text": derived_term, "origin": f"derived:{group}"})
    channels: list[Sequence[RetrievalHit]] = list(_origin_hits(connection, query, limit))
    channels.extend(_compound_variant_hits(connection, query.primary, limit))
    channels.extend(_derived_variant_hits(connection, query.primary, limit))
    if filters:
        channels.append(retrieve_structured(connection, filters, limit))
    if clause_ids:
        channels.append(retrieve_clause_ids(connection, clause_ids))
    if seed_ids:
        channels.append(traverse_relations(connection, seed_ids, graph_depth))

    direct_fused = fuse_hits(tuple(channels))[:limit]
    channels.extend(
        load_adjacent_element_hits(connection, seed)
        for seed in direct_fused
        if _is_grouped_context_seed(seed)
    )
    fused = fuse_hits(tuple(channels))[:limit]

    hit_documents = fusion_document(fused)["hits"]
    if not isinstance(hit_documents, list):
        raise RuntimeError("invalid fusion document")
    for hit_document, hit in zip(hit_documents, fused, strict=True):
        if not isinstance(hit_document, dict):
            raise RuntimeError("invalid fusion hit document")
        try:
            hit_document["citation"] = _citation_document(hit)
        except CitationUnavailableError as error:
            hit_document["citation"] = None
            hit_document["citation_unavailable_reason"] = error.reason_code
    return {
        "snapshot_hash": snapshot_hash,
        "query": {
            "primary": query.primary,
            "terms": [_query_term_document(term) for term in query.terms],
            "attempted_terms": attempted_terms,
            "derived_variants": {
                "compound": list(compound_variants),
                "entity": list(variants.entity),
                "numeric": list(variants.numeric),
                "concept": list(variants.concept),
            },
        },
        "hits": hit_documents,
    }
