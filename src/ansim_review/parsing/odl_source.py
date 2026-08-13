"""Generic metadata helpers for OpenDataLoader-style parser output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from ansim_review.parsing.pdf_geometry import normalize_bbox
from ansim_review.parsing.pdf_page_geometry import PdfPageGeometry

if TYPE_CHECKING:
    from ansim_review.parsing.odl_adapter import RawElement

ParserDimensionState = Literal["ABSENT", "VALID", "INVALID"]


@dataclass(frozen=True, slots=True)
class ParserPageDimensionsResult:
    state: ParserDimensionState
    width: float | None
    height: float | None
    origin_x: float = 0.0
    origin_y: float = 0.0
    rotation: int = 0
    box_kind: Literal["CROP_BOX", "MEDIA_BOX"] = "MEDIA_BOX"


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
        origin_x = page.get("origin_x", 0.0)
        origin_y = page.get("origin_y", 0.0)
        rotation = page.get("rotation", 0)
        box_kind = page.get("box_kind", "MEDIA_BOX")
        if (
            not isinstance(width, (int, float))
            or isinstance(width, bool)
            or not isinstance(height, (int, float))
            or isinstance(height, bool)
            or not isfinite(float(width))
            or not isfinite(float(height))
            or float(width) <= 0
            or float(height) <= 0
            or not isinstance(origin_x, (int, float))
            or isinstance(origin_x, bool)
            or not isinstance(origin_y, (int, float))
            or isinstance(origin_y, bool)
            or not isfinite(float(origin_x))
            or not isfinite(float(origin_y))
            or isinstance(rotation, bool)
            or not isinstance(rotation, int)
            or rotation % 90 != 0
            or str(box_kind) not in {"CROP_BOX", "MEDIA_BOX"}
        ):
            return ParserPageDimensionsResult("INVALID", None, None)
        return ParserPageDimensionsResult(
            "VALID",
            float(width),
            float(height),
            float(origin_x),
            float(origin_y),
            rotation % 360,
            cast(Literal["CROP_BOX", "MEDIA_BOX"], str(box_kind)),
        )
    return ParserPageDimensionsResult("ABSENT", None, None)


def normalize_odl_pdf_bbox(
    raw_bbox: tuple[float, float, float, float],
    page: PdfPageGeometry,
) -> list[float]:
    """Convert ODL PDF points to the visible CropBox-local page intersection."""
    left, bottom, right, top = (float(value) for value in raw_bbox)
    if not all(isfinite(value) for value in (left, bottom, right, top)):
        raise ValueError("bbox values must be finite")
    if left > right or bottom > top:
        raise ValueError("bbox coordinates are inverted")

    local_left = left - page.origin_x
    local_bottom = bottom - page.origin_y
    local_right = right - page.origin_x
    local_top = top - page.origin_y
    visible = (
        max(local_left, 0.0),
        max(local_bottom, 0.0),
        min(local_right, page.width),
        min(local_top, page.height),
    )
    if visible[2] <= visible[0] or visible[3] <= visible[1]:
        raise ValueError("bbox is outside page bounds")

    bbox = normalize_bbox(
        visible,
        "PDF_BOTTOM_LEFT",
        page.width,
        page.height,
    )
    return [bbox.left, bbox.bottom, bbox.right, bbox.top]


def parser_bbox(
    element: RawElement, page: PdfPageGeometry
) -> list[float] | None:
    if element.raw_bbox is None:
        return None
    return normalize_odl_pdf_bbox(element.raw_bbox, page)
