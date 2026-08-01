"""Authoritative page lookup and bbox validation for evidence records."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from ansim_review.contracts.common import BBox

DEFAULT_COORDINATE_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class PageGeometry:
    """One authoritative page identity and its canonical dimensions."""

    page_id: str
    revision_id: str
    page_number: int
    width: float
    height: float

    def __post_init__(self) -> None:
        if not self.page_id or not self.revision_id:
            raise ValueError("page identity must not be empty")
        if isinstance(self.page_number, bool) or self.page_number < 1:
            raise ValueError("page_number must be positive")
        if not isfinite(self.width) or not isfinite(self.height):
            raise ValueError("page dimensions must be finite")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("page dimensions must be positive")


def load_page_geometry(
    connection: sqlite3.Connection,
    page_id: str,
) -> PageGeometry:
    """Load one authoritative page record or reject a missing reference."""
    row = connection.execute(
        """
        SELECT id, revision_id, page_number, width, height
        FROM pages
        WHERE id = ?
        """,
        (page_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"PAGE_REFERENCE_NOT_FOUND: {page_id}")
    return PageGeometry(
        page_id=str(row[0]),
        revision_id=str(row[1]),
        page_number=int(row[2]),
        width=float(row[3]),
        height=float(row[4]),
    )


def _bbox_values(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("bbox must contain four finite numbers")
    if len(value) != 4:
        raise ValueError("bbox must contain four finite numbers")
    converted: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("bbox must contain four finite numbers")
        number = float(item)
        if not isfinite(number):
            raise ValueError("bbox values must be finite")
        converted.append(number)
    return converted[0], converted[1], converted[2], converted[3]


def validate_bbox_within_page(
    value: object,
    page: PageGeometry,
    *,
    tolerance: float = DEFAULT_COORDINATE_TOLERANCE,
) -> BBox | None:
    """Validate and normalize a nullable bbox against its referenced page."""
    if value is None:
        return None
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("coordinate tolerance must be finite and non-negative")
    left, bottom, right, top = _bbox_values(value)
    bbox = BBox(left, bottom, right, top)
    if (
        bbox.left < -tolerance
        or bbox.bottom < -tolerance
        or bbox.right > page.width + tolerance
        or bbox.top > page.height + tolerance
    ):
        raise ValueError(f"BBOX_OUT_OF_PAGE: {page.page_id}")
    return BBox(
        max(0.0, bbox.left),
        max(0.0, bbox.bottom),
        min(page.width, bbox.right),
        min(page.height, bbox.top),
    )
