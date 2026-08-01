"""OpenDataLoader JSON adapter with stable element provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias, cast

from ansim_review.canonical_json import sha256_json
from ansim_review.parsing.parser_models import (
    NormalizedParserContribution,
    PageDimensions,
    ParsedElement,
)
from ansim_review.parsing.parser_registry import ParserContext
from ansim_review.parsing.source_manifest import sha256_file

PathPart: TypeAlias = str | int
_CHILD_KEYS = ("kids", "list items", "list_items", "children")


@dataclass(frozen=True, slots=True)
class RawElement:
    element_id: str
    document_id: str
    revision_id: str
    page_number: int
    parser_order: int
    element_type: str
    source_path: tuple[PathPart, ...]
    raw_payload: dict[str, Any]
    raw_payload_hash: str
    raw_bbox: tuple[float, float, float, float] | None
    raw_text: str | None


def _page_number(payload: dict[str, Any]) -> int:
    value = payload.get("page number", payload.get("page_number"))
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("parser element page number must be a positive integer")
    return value


def _raw_bbox(payload: dict[str, Any]) -> tuple[float, float, float, float] | None:
    value = payload.get("bounding box", payload.get("bbox"))
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("parser element bounding box must contain four numbers")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("parser element bounding box must contain four numbers")
        numbers.append(float(item))
    return cast(tuple[float, float, float, float], tuple(numbers))


def _walk(
    payload: dict[str, Any],
    source_path: tuple[PathPart, ...],
    collected: list[tuple[int, tuple[PathPart, ...], dict[str, Any]]],
) -> None:
    if "type" in payload:
        collected.append((len(collected), source_path, payload))
    for key in _CHILD_KEYS:
        children = payload.get(key)
        if children is None:
            continue
        if not isinstance(children, list):
            raise ValueError(f"{key} must be an array")
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                raise ValueError(f"{key}[{index}] must be an object")
            _walk(child, (*source_path, key, index), collected)


def load_raw_elements(
    path: Path,
    document_id: str,
    revision_id: str,
) -> tuple[RawElement, ...]:
    """Flatten parser JSON and assign stable page-local element IDs."""
    if not document_id or not revision_id:
        raise ValueError("document_id and revision_id must not be empty")
    root = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(root, dict):
        raise ValueError("parser output root must be an object")

    collected: list[tuple[int, tuple[PathPart, ...], dict[str, Any]]] = []
    for key in _CHILD_KEYS:
        children = root.get(key)
        if children is None:
            continue
        if not isinstance(children, list):
            raise ValueError(f"{key} must be an array")
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                raise ValueError(f"{key}[{index}] must be an object")
            _walk(child, (key, index), collected)

    ordered = sorted(collected, key=lambda item: (_page_number(item[2]), item[0]))
    page_counts: dict[int, int] = {}
    result: list[RawElement] = []
    for parser_order, source_path, payload in ordered:
        page_number = _page_number(payload)
        page_counts[page_number] = page_counts.get(page_number, 0) + 1
        page_index = page_counts[page_number]
        element_type_value = payload.get("type")
        if not isinstance(element_type_value, str) or not element_type_value:
            raise ValueError("parser element type must be a non-empty string")
        content = payload.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("parser element content must be a string or null")
        raw_payload = dict(payload)
        result.append(
            RawElement(
                element_id=(
                    f"{document_id}-{revision_id}-P{page_number:04d}-E{page_index:05d}"
                ),
                document_id=document_id,
                revision_id=revision_id,
                page_number=page_number,
                parser_order=parser_order,
                element_type=element_type_value,
                source_path=source_path,
                raw_payload=raw_payload,
                raw_payload_hash=sha256_json(raw_payload),
                raw_bbox=_raw_bbox(payload),
                raw_text=content,
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class OpenDataLoaderJsonAdapter:
    """Normalize one OpenDataLoader JSON artifact without document identities."""

    kind: str = "OPENDATALOADER_JSON"

    def parse(self, context: ParserContext) -> NormalizedParserContribution:
        from ansim_review.parsing.odl_source import (
            parser_bbox,
            parser_document_title,
            parser_page_count,
            parser_page_dimensions,
            read_parser_json,
        )

        if context.options:
            unknown = ", ".join(sorted(context.options))
            raise ValueError(f"UNSUPPORTED_PARSER_OPTION: {unknown}")
        payload = read_parser_json(context.parser_artifact_path)
        declared_name = payload.get("file name")
        if declared_name is not None:
            if not isinstance(declared_name, str) or not declared_name.strip():
                raise ValueError("parser file name must be a non-empty string")
            if Path(declared_name).name != context.source_path.name:
                raise ValueError(
                    "PARSER_SOURCE_MISMATCH: "
                    "parser file name does not match source PDF"
                )
        raw_elements = load_raw_elements(
            context.parser_artifact_path,
            document_id="PARSER",
            revision_id="PARSER",
        )
        page_count = parser_page_count(payload, raw_elements)
        dimensions = tuple(
            PageDimensions(page_number, *parser_page_dimensions(payload, page_number))
            for page_number in range(1, page_count + 1)
        )
        size_by_page = {
            page.page_number: (page.width, page.height) for page in dimensions
        }
        page_counts: dict[int, int] = {}
        elements: list[ParsedElement] = []
        for raw in raw_elements:
            page_counts[raw.page_number] = page_counts.get(raw.page_number, 0) + 1
            index = page_counts[raw.page_number]
            width, height = size_by_page[raw.page_number]
            bbox = parser_bbox(raw, width, height)
            bbox_value = (
                None
                if bbox is None
                else (
                    float(bbox[0]),
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                )
            )
            elements.append(
                ParsedElement(
                    element_key=f"P{raw.page_number:04d}-E{index:05d}",
                    page_number=raw.page_number,
                    parser_order=raw.parser_order,
                    element_type=raw.element_type,
                    raw_payload=raw.raw_payload,
                    raw_payload_hash=raw.raw_payload_hash,
                    raw_text=raw.raw_text,
                    bbox=bbox_value,
                )
            )
        return NormalizedParserContribution(
            page_dimensions=dimensions,
            elements=tuple(elements),
            tables=(),
            visuals=(),
            parser_artifact_sha256=sha256_file(context.parser_artifact_path),
            document_title=parser_document_title(payload, context.source_path.stem),
        )
