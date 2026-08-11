"""Hybrid retrieval request execution and evidence-bundle export."""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

from ansim_review.retrieval.fusion import fuse_hits, fusion_document
from ansim_review.retrieval.graph import traverse_relations
from ansim_review.retrieval.index import require_fresh_index, search_fts
from ansim_review.retrieval.models import (
    ChannelScore,
    CitationUnavailableError,
    RetrievalHit,
)
from ansim_review.retrieval.query import NormalizedQuery, normalize_query
from ansim_review.retrieval.structured import (
    retrieve_clause_ids,
    retrieve_structured,
)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value,
        Sequence,
    ):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _strings(value: object, field: str) -> tuple[str, ...]:
    items = _sequence(value, field)
    result: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item:
            raise ValueError(
                f"{field}[{index}] must be a non-empty string"
            )
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
    return tuple(
        _mapping(item, f"expansions[{index}]")
        for index, item in enumerate(items)
    )


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
        raise ValueError(
            f"request has unknown fields: {', '.join(unknown)}"
        )
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
    return (
        normalized,
        filters,
        clause_ids,
        seed_ids,
        graph_depth,
        limit,
    )


def _origin_hits(
    connection: sqlite3.Connection,
    query: NormalizedQuery,
    limit: int,
) -> tuple[tuple[RetrievalHit, ...], ...]:
    channels: list[tuple[RetrievalHit, ...]] = []
    for term in query.terms:
        hits = search_fts(connection, term.text, limit)
        traced = tuple(
            replace(
                hit,
                channel_scores=(
                    ChannelScore(
                        "fts",
                        hit.channel_scores[0].score,
                        f"{term.origin}:{term.text}",
                    ),
                ),
            )
            for hit in hits
        )
        channels.append(traced)
    return tuple(channels)


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


def build_evidence_bundle(
    connection: sqlite3.Connection,
    request_payload: object,
) -> dict[str, object]:
    """Execute all deterministic retrieval channels and return a bundle."""
    snapshot_hash = require_fresh_index(connection)
    (
        query,
        filters,
        clause_ids,
        seed_ids,
        graph_depth,
        limit,
    ) = _normalize_request(request_payload)
    channels: list[Sequence[RetrievalHit]] = list(
        _origin_hits(connection, query, limit)
    )
    if filters:
        channels.append(retrieve_structured(connection, filters, limit))
    if clause_ids:
        channels.append(retrieve_clause_ids(connection, clause_ids))
    if seed_ids:
        channels.append(
            traverse_relations(connection, seed_ids, graph_depth)
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
            "terms": [
                {"text": term.text, "origin": term.origin}
                for term in query.terms
            ],
        },
        "hits": hit_documents,
    }
