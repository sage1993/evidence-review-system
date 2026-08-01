"""Evidence-store contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ansim_review.contracts.common import BBox


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Traceable source or derived evidence record."""

    evidence_id: str
    document_id: str
    revision_id: str
    page_number: int
    element_id: str
    evidence_type: str
    bbox: BBox
    source_hash: str
    raw_text: str | None = None
    normalized_text: str | None = None
