"""Generic metadata helpers for OpenDataLoader-style parser output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ansim_review.parsing.pdf_geometry import normalize_bbox

if TYPE_CHECKING:
    from ansim_review.parsing.odl_adapter import RawElement

ParserDimensionState = Literal["ABSENT", "VALID", "INVALID"]


@dataclass(frozen=True, slots=True)
class ParserPageDimensionsResult:
    state: ParserDimensionState
    width: float | None
    height: float | None


def read_parser_json(path: Path) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    if not all(isinstance(key, str) for key in payload):
        raise ValueError(f"{path} root keys must be strings")
    return {str(key): value for key, value in payload.items()}


def _validate_element_page_bounds(
    elements: tuple[RawElement, ...], page_count: int
) -> None:
    for item in elements:
        if not 1 <= item.page_number <= page_count:
            raise ValueError(
                "PARSER_ELEMENT_PAGE_OUT_OF_RANGE: "
                f"page={item.page_number} page_count={page_count} "
                f"source_path={item.source_path!r}"
            )


def parser_page_count(
    payload: Mapping[str, Any], elements: tuple[RawElement, ...]
) -> int:
    value = payload.get("number of pages", payload.get("page_count"))
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        page_count = value
    elif elements:
        page_count = max(item.page_number for item in elements)
    else:
        raise ValueError("parser output does not declare a positive page count")
    _validate_element_page_bounds(elements, page_count)
    return page_count


def parser_document_title(payload: Mapping[str, Any], fallback: str) -> str:
    title = payload.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    kids = payload.get("kids")
    if isinstance(kids, list):
        for item in kids:
            if isinstance(item, dict) and item.get("type") == "heading":
                content = item.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    return fallback


def parser_page_dimensions(
    payload: Mapping[str, Any], page_number: int
) -> ParserPageDimensionsResult:
    pages = payload.get("pages")
    if pages is None:
        return ParserPageDimensionsResult("ABSENT", None, None)
    if not isinstance(pages, list):
        return ParserPageDimensionsResult("INVALID", None, None)
    for page in pages:
        if not isinstance(page, dict):
            continue
        number = page.get("page_number", page.get("page number"))
        if number != page_number:
            continue
        has_width = "width" in page
        has_height = "height" in page
        if not has_width and not has_height:
            return ParserPageDimensionsResult("ABSENT", None, None)
        width = page.get("width")
        height = page.get("height")
        if (
            isinstance(width, (int, float))
            and not isinstance(width, bool)
            and isinstance(height, (int, float))
            and not isinstance(height, bool)
            and isfinite(float(width))
            and isfinite(float(height))
            and float(width) > 0
            and float(height) > 0
        ):
            return ParserPageDimensionsResult("VALID", float(width), float(height))
        return ParserPageDimensionsResult("INVALID", None, None)
    return ParserPageDimensionsResult("ABSENT", None, None)


def parser_bbox(
    element: RawElement, width: float, height: float
) -> list[float] | None:
    if element.raw_bbox is None:
        return None
    bbox = normalize_bbox(element.raw_bbox, "PDF_BOTTOM_LEFT", width, height)
    return [bbox.left, bbox.bottom, bbox.right, bbox.top]
