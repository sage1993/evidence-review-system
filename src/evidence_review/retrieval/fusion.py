"""Deterministic weighted fusion for hybrid evidence channels."""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from evidence_review.retrieval.models import RetrievalHit

CHANNEL_WEIGHTS: dict[str, Decimal] = {
    "structured_exact": Decimal("1.00"),
    "clause_id": Decimal("0.95"),
    "rule_source": Decimal("0.90"),
    "fts_phrase": Decimal("0.55"),
    "fts_entity": Decimal("0.40"),
    "fts_korean_compound": Decimal("0.35"),
    "fts_numeric": Decimal("0.20"),
    "fts_token_and": Decimal("0.15"),
    "fts_concept": Decimal("0.10"),
    "structural_context": Decimal("0.08"),
    "linked_visual_table": Decimal("0.60"),
}


def _same_identity(left: RetrievalHit, right: RetrievalHit) -> bool:
    return (
        left.evidence_type == right.evidence_type
        and left.document_id == right.document_id
        and left.revision_id == right.revision_id
        and left.page_number == right.page_number
        and left.bbox == right.bbox
        and left.source_hash == right.source_hash
        and left.title == right.title
        and left.text == right.text
    )


def _merge(existing: RetrievalHit, incoming: RetrievalHit) -> RetrievalHit:
    if not _same_identity(existing, incoming):
        raise ValueError(f"conflicting retrieval identity for {existing.evidence_id}")
    merged = existing
    for channel in incoming.channel_scores:
        merged = merged.with_channel(channel)
    for match in incoming.matches:
        merged = merged.with_match(match)
    return merged


def _score(hit: RetrievalHit) -> Decimal:
    score = Decimal("0")
    for channel in hit.channel_scores:
        try:
            weight = CHANNEL_WEIGHTS[channel.channel]
        except KeyError as error:
            raise ValueError(f"unsupported retrieval channel: {channel.channel}") from error
        score += weight * channel.score
    return score


def fuse_hits(
    channels: Sequence[Sequence[RetrievalHit]],
) -> tuple[RetrievalHit, ...]:
    """Merge channel hits and sort by descending weighted score then stable ID."""
    by_id: dict[str, RetrievalHit] = {}
    for channel_hits in channels:
        for hit in channel_hits:
            existing = by_id.get(hit.evidence_id)
            by_id[hit.evidence_id] = hit if existing is None else _merge(existing, hit)
    scored = [hit.with_final_score(_score(hit)) for hit in by_id.values()]
    scored.sort(key=lambda item: (-item.final_score, item.evidence_id))
    return tuple(scored)


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _bbox_document(hit: RetrievalHit) -> list[float] | None:
    if hit.bbox is None:
        return None
    return [
        hit.bbox.left,
        hit.bbox.bottom,
        hit.bbox.right,
        hit.bbox.top,
    ]


def _hit_document(hit: RetrievalHit) -> dict[str, object]:
    document: dict[str, object] = {
        "evidence_id": hit.evidence_id,
        "evidence_type": hit.evidence_type,
        "document_id": hit.document_id,
        "revision_id": hit.revision_id,
        "page_number": hit.page_number,
        "bbox": _bbox_document(hit),
        "citation_quality": hit.citation_quality.value,
        "source_hash": hit.source_hash,
        "title": hit.title,
        "text": hit.text,
        "channel_scores": [
            {
                "channel": channel.channel,
                "score": _decimal_text(channel.score),
                "detail": channel.detail,
            }
            for channel in hit.channel_scores
        ],
        "final_score": _decimal_text(hit.final_score),
    }
    if hit.matches:
        document["matches"] = [
            {
                "search_request_id": match.search_request_id,
                "issue_ids": list(match.issue_ids),
                "query_text": match.query_text,
                "origin": match.origin,
            }
            for match in hit.matches
        ]
    return document


def fusion_document(hits: Sequence[RetrievalHit]) -> dict[str, object]:
    """Return canonical JSON-ready fused evidence output."""
    return {"hits": [_hit_document(hit) for hit in hits]}
