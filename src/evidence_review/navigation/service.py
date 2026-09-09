"""Read-only deterministic navigation over a finalized evidence database."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from evidence_review.contracts.common import BBox, Citation
from evidence_review.evidence.finalization import validate_finalized_evidence
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.navigation.models import NavigationHit, NavigationResult
from evidence_review.retrieval.bundle import build_evidence_bundle
from evidence_review.review_question import canonical_query_request


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return value


def _bbox(value: object, field: str) -> BBox:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{field} must contain four numbers")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise ValueError(f"{field} must contain four numbers")
    return BBox(*(float(item) for item in value))


def _hit(value: object, index: int) -> NavigationHit | None:
    payload = _mapping(value, f"hits[{index}]")
    citation_payload = payload.get("citation")
    if citation_payload is None:
        # Page-only retrieval is not a promotable navigation hit. Keep the
        # navigation contract exact and traceable rather than fabricating a bbox.
        return None
    citation = _mapping(citation_payload, f"hits[{index}].citation")
    evidence_id = payload.get("evidence_id")
    evidence_type = payload.get("evidence_type")
    document_id = payload.get("document_id")
    revision_id = payload.get("revision_id")
    page_number = payload.get("page_number")
    source_hash = payload.get("source_hash")
    title = payload.get("title")
    text = payload.get("text")
    score = payload.get("final_score", "0")
    if not all(
        isinstance(item, str) and item
        for item in (evidence_id, evidence_type, document_id, revision_id, source_hash, title, text)
    ):
        raise ValueError(f"hits[{index}] has invalid identity or text")
    assert isinstance(evidence_id, str)
    assert isinstance(evidence_type, str)
    assert isinstance(document_id, str)
    assert isinstance(revision_id, str)
    assert isinstance(source_hash, str)
    assert isinstance(title, str)
    assert isinstance(text, str)
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        raise ValueError(f"hits[{index}].page_number must be a positive integer")
    citation_bbox = _bbox(citation.get("bbox"), f"hits[{index}].citation.bbox")
    citation_fields = (
        citation.get("citation_id"),
        citation.get("document_id"),
        citation.get("revision_id"),
        citation.get("evidence_id"),
        citation.get("source_hash"),
    )
    if not all(isinstance(item, str) and item for item in citation_fields):
        raise ValueError(f"hits[{index}].citation has invalid identity")
    citation_id = citation["citation_id"]
    citation_document_id = citation["document_id"]
    citation_revision_id = citation["revision_id"]
    citation_evidence_id = citation["evidence_id"]
    citation_source_hash = citation["source_hash"]
    assert isinstance(citation_id, str)
    assert isinstance(citation_document_id, str)
    assert isinstance(citation_revision_id, str)
    assert isinstance(citation_evidence_id, str)
    assert isinstance(citation_source_hash, str)
    citation_page = citation.get("page_number")
    if isinstance(citation_page, bool) or not isinstance(citation_page, int):
        raise ValueError(f"hits[{index}].citation.page_number must be an integer")
    if (
        citation["evidence_id"] != evidence_id
        or citation["document_id"] != document_id
        or citation["revision_id"] != revision_id
        or citation["page_number"] != page_number
        or citation["source_hash"] != source_hash
    ):
        raise ValueError(f"hits[{index}] citation identity does not match hit")
    try:
        decimal_score = Decimal(str(score))
    except ArithmeticError as error:
        raise ValueError(f"hits[{index}].final_score must be numeric") from error
    return NavigationHit(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        document_id=document_id,
        revision_id=revision_id,
        page_number=page_number,
        bbox=citation_bbox,
        source_hash=source_hash,
        title=title,
        text=text,
        score=decimal_score,
        citation=Citation(
            citation_id=citation_id,
            document_id=citation_document_id,
            revision_id=citation_revision_id,
            page_number=citation_page,
            evidence_id=citation_evidence_id,
            bbox=citation_bbox,
            source_hash=citation_source_hash,
        ),
    )


def navigate_evidence(
    evidence_db: Path,
    query: str,
    limit: int = 20,
) -> NavigationResult:
    """Search finalized evidence without creating any formal-review artifact."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    database = Path(evidence_db)
    with EvidenceStore(database, read_only=True) as store:
        validate_finalized_evidence(store)
        query_request = canonical_query_request(query, ())
        query_request["limit"] = limit
        bundle = build_evidence_bundle(
            store.require_connection(), query_request
        )
        provenance = finalized_evidence_provenance(database)
    raw_hits = bundle.get("hits")
    if not isinstance(raw_hits, list):
        raise ValueError("navigation bundle hits must be an array")
    hits = tuple(
        item
        for index, value in enumerate(raw_hits[:limit])
        if (item := _hit(value, index)) is not None
    )
    snapshot_hash = provenance.get("evidence_snapshot_hash")
    database_sha = provenance.get("evidence_db_sha256")
    if not isinstance(snapshot_hash, str) or not isinstance(database_sha, str):
        raise ValueError("finalized evidence provenance is incomplete")
    return NavigationResult(
        query=" ".join(query.split()),
        evidence_snapshot_hash=snapshot_hash,
        evidence_db_sha256=database_sha,
        hits=hits,
    )
