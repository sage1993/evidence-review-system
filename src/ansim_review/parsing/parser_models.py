"""Parser-neutral contribution models for generic evidence ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite
from typing import Any

from ansim_review.contracts.common import BBox
from ansim_review.evidence.page_geometry import PageGeometry, validate_bbox_within_page

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
BBoxValue = tuple[float, float, float, float]


def _require_key(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")


def _require_hash(value: str, field: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class PageDimensions:
    """One parser-declared page number and dimensions."""

    page_number: int
    width: float
    height: float

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or self.page_number < 1:
            raise ValueError("page_number must be positive")
        if not isfinite(self.width) or not isfinite(self.height):
            raise ValueError("page dimensions must be finite")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("page dimensions must be positive")


@dataclass(frozen=True, slots=True)
class ParsedElement:
    element_key: str
    page_number: int
    parser_order: int
    element_type: str
    raw_payload: dict[str, Any]
    raw_payload_hash: str
    raw_text: str | None
    bbox: BBoxValue | None

    def __post_init__(self) -> None:
        _require_key(self.element_key, "element_key")
        _require_key(self.element_type, "element_type")
        _require_hash(self.raw_payload_hash, "raw_payload_hash")
        if isinstance(self.page_number, bool) or self.page_number < 1:
            raise ValueError("page_number must be positive")
        if isinstance(self.parser_order, bool) or self.parser_order < 0:
            raise ValueError("parser_order must be non-negative")
        if self.raw_text is not None and not isinstance(self.raw_text, str):
            raise ValueError("raw_text must be a string or null")


@dataclass(frozen=True, slots=True)
class ParsedTable:
    table_key: str
    page_number: int
    raw_payload: dict[str, Any]
    raw_payload_hash: str
    bbox: BBoxValue | None

    def __post_init__(self) -> None:
        _require_key(self.table_key, "table_key")
        _require_hash(self.raw_payload_hash, "raw_payload_hash")
        if isinstance(self.page_number, bool) or self.page_number < 1:
            raise ValueError("page_number must be positive")


@dataclass(frozen=True, slots=True)
class ParsedVisual:
    visual_key: str
    page_number: int
    kind: str
    relative_path: str
    sha256: str
    bbox: BBoxValue | None

    def __post_init__(self) -> None:
        _require_key(self.visual_key, "visual_key")
        _require_key(self.kind, "kind")
        _require_key(self.relative_path, "relative_path")
        _require_hash(self.sha256, "sha256")
        if isinstance(self.page_number, bool) or self.page_number < 1:
            raise ValueError("page_number must be positive")


@dataclass(frozen=True, slots=True)
class NormalizedParserContribution:
    """One parser artifact projected into source-relative evidence records."""

    page_dimensions: tuple[PageDimensions, ...]
    elements: tuple[ParsedElement, ...]
    tables: tuple[ParsedTable, ...]
    visuals: tuple[ParsedVisual, ...]
    parser_artifact_sha256: str

    def __post_init__(self) -> None:
        _require_hash(self.parser_artifact_sha256, "parser_artifact_sha256")
        page_numbers = tuple(page.page_number for page in self.page_dimensions)
        expected = tuple(range(1, len(self.page_dimensions) + 1))
        if page_numbers != expected:
            raise ValueError("PARSER_PAGE_SEQUENCE")
        pages = {page.page_number: page for page in self.page_dimensions}
        keys: set[tuple[str, str]] = set()
        records = (
            *(("element", item.element_key, item.page_number, item.bbox) for item in self.elements),
            *(("table", item.table_key, item.page_number, item.bbox) for item in self.tables),
            *(("visual", item.visual_key, item.page_number, item.bbox) for item in self.visuals),
        )
        for kind, key, page_number, bbox in records:
            identity = (kind, key)
            if identity in keys:
                raise ValueError(f"PARSER_RECORD_DUPLICATE: {kind}:{key}")
            keys.add(identity)
            page = pages.get(page_number)
            if page is None:
                raise ValueError(f"PARSER_PAGE_NOT_FOUND: {page_number}")
            validate_bbox_within_page(
                bbox,
                PageGeometry(
                    page_id=f"PARSER-P{page_number:04d}",
                    revision_id="PARSER",
                    page_number=page_number,
                    width=page.width,
                    height=page.height,
                ),
            )

    @property
    def page_count(self) -> int:
        return len(self.page_dimensions)


def bbox_tuple(value: BBox | None) -> BBoxValue | None:
    """Project a canonical BBox into a JSON-ready tuple."""
    if value is None:
        return None
    return (value.left, value.bottom, value.right, value.top)
