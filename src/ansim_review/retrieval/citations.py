"""Exact source citation resolution against immutable evidence."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ansim_review.contracts.common import BBox, Citation
from ansim_review.contracts.evidence import EvidenceRecord


@dataclass(frozen=True, slots=True)
class CitationResolution:
    citation_id: str
    evidence_id: str
    resolved: bool
    error_codes: tuple[str, ...]


def _bbox_matches(left: BBox, right: BBox, tolerance: float) -> bool:
    return all(
        abs(a - b) <= tolerance
        for a, b in zip(
            (left.left, left.bottom, left.right, left.top),
            (right.left, right.bottom, right.right, right.top),
            strict=True,
        )
    )


def resolve_citation(
    citation: Citation,
    evidence: Mapping[str, EvidenceRecord] | Sequence[EvidenceRecord],
    *,
    bbox_tolerance: float = 0.01,
) -> CitationResolution:
    """Resolve one citation using immutable source identity fields."""
    if bbox_tolerance < 0:
        raise ValueError("bbox_tolerance must not be negative")
    if isinstance(evidence, Mapping):
        evidence_map = dict(evidence)
    else:
        evidence_map = {
            record.evidence_id: record for record in evidence
        }
    record = evidence_map.get(citation.evidence_id)
    if record is None:
        return CitationResolution(
            citation.citation_id,
            citation.evidence_id,
            False,
            ("UNRESOLVED_CITATION",),
        )

    errors: list[str] = []
    if (
        record.document_id != citation.document_id
        or record.revision_id != citation.revision_id
    ):
        errors.append("CITATION_IDENTITY_MISMATCH")
    if record.page_number != citation.page_number:
        errors.append("CITATION_PAGE_MISMATCH")
    if record.source_hash != citation.source_hash:
        errors.append("SOURCE_HASH_MISMATCH")
    if not _bbox_matches(record.bbox, citation.bbox, bbox_tolerance):
        errors.append("CITATION_BBOX_MISMATCH")
    return CitationResolution(
        citation.citation_id,
        citation.evidence_id,
        not errors,
        tuple(errors),
    )
