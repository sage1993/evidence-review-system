"""Immutable navigation result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from evidence_review.contracts.common import BBox, Citation


@dataclass(frozen=True, slots=True)
class NavigationHit:
    """One exact, citable result from finalized evidence."""

    evidence_id: str
    document_id: str
    revision_id: str
    page_number: int
    bbox: BBox
    source_hash: str
    title: str
    text: str
    score: Decimal
    citation: Citation


@dataclass(frozen=True, slots=True)
class NavigationResult:
    """Read-only navigation output bound to one finalized evidence artifact."""

    query: str
    evidence_snapshot_hash: str
    evidence_db_sha256: str
    hits: tuple[NavigationHit, ...]
