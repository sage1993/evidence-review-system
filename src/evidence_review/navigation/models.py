"""Immutable contracts for non-authoritative evidence navigation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from evidence_review.contracts.common import BBox, Citation


@dataclass(frozen=True, slots=True)
class NavigationHit:
    """One traceable hit from a finalized evidence navigation query."""

    evidence_id: str
    evidence_type: str
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
    """Read-only exploration result; it cannot carry a formal status."""

    query: str
    evidence_snapshot_hash: str
    hits: tuple[NavigationHit, ...]
    evidence_db_sha256: str | None = None
    formal_status: Literal[None] = None
