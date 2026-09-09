"""Read-only navigation over finalized evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import expect_sha256
from evidence_review.evidence.finalization import validate_finalized_evidence
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.navigation.models import NavigationHit, NavigationResult
from evidence_review.navigation.query import navigation_request
from evidence_review.retrieval.bundle import build_evidence_bundle


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return value


def _bbox(value: object, field: str) -> BBox:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must contain four numbers")
    if len(value) != 4:
        raise ValueError(f"{field} must contain four numbers")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{field} must contain four numbers")
        numbers.append(float(item))
    return BBox(*numbers)


def _identifier(value: object, field: str) -> str:
    return validate_identifier(value, field)


def _page_number(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def _score(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("final_score must be a decimal")
    try:
        score = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("final_score must be a decimal") from error
    if not score.is_finite():
        raise ValueError("final_score must be finite")
    return score


def _citation(value: object, hit: Mapping[str, object]) -> Citation:
    citation = _mapping(value, "citation")
    required = {
        "citation_id",
        "document_id",
        "revision_id",
        "page_number",
        "evidence_id",
        "bbox",
        "source_hash",
    }
    if set(citation) != required:
        raise ValueError("citation fields are invalid")
    evidence_id = _identifier(citation.get("evidence_id"), "citation.evidence_id")
    document_id = _identifier(citation.get("document_id"), "citation.document_id")
    revision_id = _identifier(citation.get("revision_id"), "citation.revision_id")
    page_number = _page_number(citation.get("page_number"), "citation.page_number")
    bbox = _bbox(citation.get("bbox"), "citation.bbox")
    source_hash = expect_sha256(citation.get("source_hash"), "citation.source_hash")
    citation_id = _text(citation.get("citation_id"), "citation.citation_id")
    if citation_id != f"CIT-{evidence_id}":
        raise ValueError("citation identity mismatch")

    hit_identity = (
        _identifier(hit.get("evidence_id"), "hit.evidence_id"),
        _identifier(hit.get("document_id"), "hit.document_id"),
        _identifier(hit.get("revision_id"), "hit.revision_id"),
        _page_number(hit.get("page_number"), "hit.page_number"),
        _bbox(hit.get("bbox"), "hit.bbox"),
        expect_sha256(hit.get("source_hash"), "hit.source_hash"),
    )
    citation_identity = (
        evidence_id,
        document_id,
        revision_id,
        page_number,
        bbox,
        source_hash,
    )
    if citation_identity != hit_identity:
        raise ValueError("citation identity mismatch")
    return Citation(
        citation_id=citation_id,
        document_id=document_id,
        revision_id=revision_id,
        page_number=page_number,
        evidence_id=evidence_id,
        bbox=bbox,
        source_hash=source_hash,
    )


def _navigation_hit(value: object) -> NavigationHit | None:
    hit = _mapping(value, "hit")
    if hit.get("citation_quality") == "PAGE_ONLY":
        return None
    citation_value = hit.get("citation")
    if citation_value is None:
        raise ValueError("citation is required")
    citation = _citation(citation_value, hit)
    return NavigationHit(
        evidence_id=citation.evidence_id,
        document_id=citation.document_id,
        revision_id=citation.revision_id,
        page_number=citation.page_number,
        bbox=citation.bbox,
        source_hash=citation.source_hash,
        title=_text(hit.get("title"), "hit.title"),
        text=_text(hit.get("text"), "hit.text"),
        score=_score(hit.get("final_score")),
        citation=citation,
    )


def navigate_evidence(
    evidence_db: Path,
    query: str,
    *,
    limit: int = 20,
) -> NavigationResult:
    """Search exact finalized evidence without creating any review authority."""
    normalized_query, request = navigation_request(query, limit=limit)
    database = Path(evidence_db)
    with EvidenceStore(database, read_only=True) as store:
        state = validate_finalized_evidence(store)
        bundle = _mapping(build_evidence_bundle(store.require_connection(), request), "bundle")
        bundle_snapshot = expect_sha256(bundle.get("snapshot_hash"), "bundle.snapshot_hash")
        raw_hits = bundle.get("hits")
        if isinstance(raw_hits, (str, bytes, bytearray)) or not isinstance(raw_hits, Sequence):
            raise ValueError("bundle.hits must be an array")
        hits = tuple(
            hit
            for item in raw_hits
            if (hit := _navigation_hit(item)) is not None
        )
        if bundle_snapshot != state.snapshot_hash:
            raise ValueError("navigation bundle snapshot mismatch")
    provenance = finalized_evidence_provenance(database)
    evidence_snapshot_hash = expect_sha256(
        provenance.get("evidence_snapshot_hash"), "evidence_snapshot_hash"
    )
    evidence_db_sha256 = expect_sha256(
        provenance.get("evidence_db_sha256"), "evidence_db_sha256"
    )
    if evidence_snapshot_hash != bundle_snapshot:
        raise ValueError("navigation evidence snapshot changed")
    return NavigationResult(
        query=normalized_query,
        evidence_snapshot_hash=evidence_snapshot_hash,
        evidence_db_sha256=evidence_db_sha256,
        hits=hits,
    )
