"""Common source-identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class BBox:
    """Canonical PDF bounding box in left, bottom, right, top order."""

    left: float
    bottom: float
    right: float
    top: float

    def __post_init__(self) -> None:
        values = (self.left, self.bottom, self.right, self.top)
        if not all(isfinite(value) for value in values):
            raise ValueError("bbox values must be finite")
        if self.left > self.right or self.bottom > self.top:
            raise ValueError("bbox coordinates are inverted")


@dataclass(frozen=True, slots=True)
class Citation:
    """Resolved citation to immutable source evidence."""

    citation_id: str
    document_id: str
    revision_id: str
    page_number: int
    evidence_id: str
    bbox: BBox
    source_hash: str

    def __post_init__(self) -> None:
        if self.citation_id != f"CIT-{self.evidence_id}":
            raise ValueError(
                "citation_id must equal CIT- followed by evidence_id"
            )
