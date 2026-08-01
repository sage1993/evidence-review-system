"""Generic metadata helpers for OpenDataLoader-style parser output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ansim_review.parsing.odl_adapter import RawElement
from ansim_review.parsing.pdf_geometry import normalize_bbox

_DEFAULT_PAGE_WIDTH = 595.0
_DEFAULT_PAGE_HEIGHT = 842.0


def read_parser_json(path: Path) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    if not all(isinstance(key, str) for key in payload):
        raise ValueError(f"{path} root keys must be strings")
    return {str(key): value for key, value in payload.items()}


def parser_page_count(
    payload: Mapping[str, Any], elements: tuple[RawElement, ...]
) -> int:
    value = payload.get("number of pages", payload.get("page_count"))
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if elements:
        return max(item.page_number for item in elements)
    raise ValueError("parser output does not declare a positive page count")


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
) -> tuple[float, float]:
    pages = payload.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            number = page.get("page_number", page.get("page number"))
            if number != page_number:
                continue
            width = page.get("width")
            height = page.get("height")
            if (
                isinstance(width, (int, float))
                and not isinstance(width, bool)
                and isinstance(height, (int, float))
                and not isinstance(height, bool)
                and float(width) > 0
                and float(height) > 0
            ):
                return float(width), float(height)
    return _DEFAULT_PAGE_WIDTH, _DEFAULT_PAGE_HEIGHT


def parser_bbox(
    element: RawElement, width: float, height: float
) -> list[float] | None:
    if element.raw_bbox is None:
        return None
    bbox = normalize_bbox(element.raw_bbox, "PDF_BOTTOM_LEFT", width, height)
    return [bbox.left, bbox.bottom, bbox.right, bbox.top]
