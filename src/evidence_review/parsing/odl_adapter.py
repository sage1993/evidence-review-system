"""OpenDataLoader JSON adapter with stable element provenance."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from evidence_review.canonical_json import sha256_json
from evidence_review.parsing.odl_source import (
    parser_bbox,
    parser_document_title,
    parser_page_count,
    parser_page_dimensions,
    read_parser_json,
)
from evidence_review.parsing.parser_models import (
    NormalizedParserContribution,
    PageDimensions,
    ParsedElement,
    ParsedTable,
    ParsedTableCell,
    ParsedTableRow,
)
from evidence_review.parsing.parser_registry import ParserContext
from evidence_review.parsing.pdf_page_geometry import PdfPageGeometry, read_pdf_page_geometries
from evidence_review.parsing.source_manifest import sha256_file

type PathPart = str | int
_CHILD_KEYS = ("kids", "list items", "list_items", "children")
_TABLE_ROW_KEYS = ("rows",)
_TABLE_CELL_KEYS = ("cells",)
_GEOMETRY_TOLERANCE = 0.5


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


def _positive_int(value: object, field: str, *, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nested_content(payload: dict[str, Any]) -> tuple[str, ...]:
    """Collect text from a parser node without flattening table relationships."""
    parts: list[str] = []
    content = payload.get("content")
    if content is not None:
        if not isinstance(content, str):
            raise ValueError("parser table content must be a string or null")
        if content.strip():
            parts.append(content.strip())
    for key in _CHILD_KEYS:
        children = payload.get(key)
        if children is None:
            continue
        if not isinstance(children, list):
            raise ValueError(f"{key} must be an array")
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                raise ValueError(f"{key}[{index}] must be an object")
            parts.extend(_nested_content(child))
    return tuple(parts)


def _table_search_text(payload: dict[str, Any]) -> str:
    """Build a row/column-aware representation suitable for lexical search."""
    rows = payload.get("rows", [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("rows must be an array")
    segments: list[str] = []
    for row_index, raw_row in enumerate(rows, start=1):
        if not isinstance(raw_row, dict):
            raise ValueError(f"rows[{row_index - 1}] must be an object")
        row_number = _positive_int(
            raw_row.get("row number", raw_row.get("row_number")),
            f"rows[{row_index - 1}].row_number",
            default=row_index,
        )
        cells = raw_row.get("cells", [])
        if not isinstance(cells, list):
            raise ValueError(f"rows[{row_index - 1}].cells must be an array")
        for cell_index, raw_cell in enumerate(cells, start=1):
            if not isinstance(raw_cell, dict):
                raise ValueError(
                    f"rows[{row_index - 1}].cells[{cell_index - 1}] must be an object"
                )
            column_number = _positive_int(
                raw_cell.get("column number", raw_cell.get("column_number")),
                f"rows[{row_index - 1}].cells[{cell_index - 1}].column_number",
                default=cell_index,
            )
            text = " ".join(_nested_content(raw_cell))
            if text:
                segments.append(f"행 {row_number} 열 {column_number}: {text}")
    if not segments:
        direct = " ".join(_nested_content(payload))
        return f"표: {direct}" if direct else ""
    return " | ".join(segments)


def _raw_parser_table_id(payload: dict[str, Any]) -> str | int | None:
    value = payload.get("id")
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int):
        return value
    return None


def _canonical_table_id(
    *,
    source_revision_id: str,
    page_number: int,
    raw_parser_table_id: str | int | None,
    structural_path: tuple[PathPart, ...],
) -> str:
    identity = {
        "source_revision_id": source_revision_id,
        "page_number": page_number,
        "raw_parser_table_id": raw_parser_table_id,
        "structural_path": list(structural_path),
    }
    return f"T-{sha256_json(identity).upper()}"


def _collect_table_payloads(
    payload: dict[str, Any],
    source_path: tuple[PathPart, ...],
    collected: list[tuple[tuple[PathPart, ...], dict[str, Any]]],
) -> None:
    if payload.get("type") == "table":
        collected.append((source_path, payload))
    for key in _CHILD_KEYS:
        children = payload.get(key)
        if children is None:
            continue
        if not isinstance(children, list):
            raise ValueError(f"{key} must be an array")
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                raise ValueError(f"{key}[{index}] must be an object")
            _collect_table_payloads(child, (*source_path, key, index), collected)


def _parsed_table(
    payload: dict[str, Any],
    source_path: tuple[PathPart, ...],
    source_revision_id: str,
) -> ParsedTable:
    page_number = _page_number(payload)
    raw_parser_table_id = _raw_parser_table_id(payload)
    rows_value = payload.get("rows", [])
    if rows_value is None:
        rows_value = []
    if not isinstance(rows_value, list):
        raise ValueError("rows must be an array")
    rows: list[ParsedTableRow] = []
    for row_index, raw_row in enumerate(rows_value, start=1):
        if not isinstance(raw_row, dict):
            raise ValueError(f"rows[{row_index - 1}] must be an object")
        row_number = _positive_int(
            raw_row.get("row number", raw_row.get("row_number")),
            f"rows[{row_index - 1}].row_number",
            default=row_index,
        )
        cells_value = raw_row.get("cells", [])
        if not isinstance(cells_value, list):
            raise ValueError(f"rows[{row_index - 1}].cells must be an array")
        cells: list[ParsedTableCell] = []
        for cell_index, raw_cell in enumerate(cells_value, start=1):
            if not isinstance(raw_cell, dict):
                raise ValueError(
                    f"rows[{row_index - 1}].cells[{cell_index - 1}] must be an object"
                )
            cell_page = raw_cell.get("page number", raw_cell.get("page_number"))
            if cell_page is not None and _positive_int(
                cell_page,
                f"rows[{row_index - 1}].cells[{cell_index - 1}].page_number",
            ) != page_number:
                raise ValueError("PARSER_TABLE_CELL_PAGE_MISMATCH")
            column_number = _positive_int(
                raw_cell.get("column number", raw_cell.get("column_number")),
                f"rows[{row_index - 1}].cells[{cell_index - 1}].column_number",
                default=cell_index,
            )
            row_span = _positive_int(
                raw_cell.get("row span", raw_cell.get("row_span")),
                f"rows[{row_index - 1}].cells[{cell_index - 1}].row_span",
                default=1,
            )
            column_span = _positive_int(
                raw_cell.get("column span", raw_cell.get("column_span")),
                f"rows[{row_index - 1}].cells[{cell_index - 1}].column_span",
                default=1,
            )
            cells.append(
                ParsedTableCell(
                    row_number=row_number,
                    column_number=column_number,
                    row_span=row_span,
                    column_span=column_span,
                    raw_payload=dict(raw_cell),
                    raw_payload_hash=sha256_json(raw_cell),
                    text=" ".join(_nested_content(raw_cell)) or None,
                    bbox=_raw_bbox(raw_cell),
                )
            )
        rows.append(ParsedTableRow(row_number=row_number, cells=tuple(cells)))
    return ParsedTable(
        table_key=_canonical_table_id(
            source_revision_id=source_revision_id,
            page_number=page_number,
            raw_parser_table_id=raw_parser_table_id,
            structural_path=source_path,
        ),
        page_number=page_number,
        raw_payload=dict(payload),
        raw_payload_hash=sha256_json(payload),
        bbox=_raw_bbox(payload),
        rows=tuple(rows),
        search_text=_table_search_text(payload),
        raw_parser_table_id=raw_parser_table_id,
        source_revision_id=source_revision_id,
        structural_path=source_path,
    )


def load_parsed_tables(
    path: Path,
    document_id: str,
    revision_id: str,
) -> tuple[ParsedTable, ...]:
    """Load tables with deterministic source-revision-bound identities.

    ``document_id`` is accepted to keep the binding signature parallel with
    ``load_raw_elements``. The raw parser ID remains a separate provenance
    value and never becomes the canonical table identity on its own.
    """
    if not document_id or not revision_id:
        raise ValueError("document_id and revision_id must not be empty")
    root = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(root, dict):
        raise ValueError("parser output root must be an object")
    collected: list[tuple[tuple[PathPart, ...], dict[str, Any]]] = []
    for key in _CHILD_KEYS:
        children = root.get(key)
        if children is None:
            continue
        if not isinstance(children, list):
            raise ValueError(f"{key} must be an array")
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                raise ValueError(f"{key}[{index}] must be an object")
            _collect_table_payloads(child, (key, index), collected)
    tables = tuple(
        _parsed_table(payload, source_path, revision_id)
        for source_path, payload in collected
    )
    canonical_ids = [table.canonical_table_id for table in tables]
    if len(canonical_ids) != len(set(canonical_ids)):
        raise ValueError("PARSER_TABLE_IDENTITY_COLLISION")
    return tables


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
        if element_type_value == "table" and content is None:
            content = _table_search_text(payload) or None
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


def _reconcile_page_dimensions(
    payload: Mapping[str, Any],
    page_count: int,
    pdf_pages: tuple[PdfPageGeometry, ...],
) -> tuple[PageDimensions, ...]:
    if len(pdf_pages) != page_count:
        raise ValueError(
            "PARSER_PDF_PAGE_COUNT_MISMATCH: "
            f"parser={page_count} pdf={len(pdf_pages)}"
        )

    dimensions: list[PageDimensions] = []
    for pdf_page in pdf_pages:
        declared = parser_page_dimensions(payload, pdf_page.page_number)
        if declared.state == "INVALID":
            raise ValueError(
                f"PARSER_PAGE_DIMENSIONS_INVALID: page {pdf_page.page_number}"
            )
        if declared.state == "VALID":
            assert declared.width is not None
            assert declared.height is not None
            if (
                abs(declared.width - pdf_page.width) > _GEOMETRY_TOLERANCE
                or abs(declared.height - pdf_page.height) > _GEOMETRY_TOLERANCE
            ):
                raise ValueError(
                    "PARSER_PDF_PAGE_DIMENSIONS_MISMATCH: "
                    f"page {pdf_page.page_number} "
                    f"parser={declared.width}x{declared.height} "
                    f"pdf={pdf_page.width}x{pdf_page.height}"
                )
        dimensions.append(
            PageDimensions(
                pdf_page.page_number,
                pdf_page.width,
                pdf_page.height,
                pdf_page.origin_x,
                pdf_page.origin_y,
                pdf_page.rotation,
                pdf_page.box_kind,
            )
        )
    return tuple(dimensions)


def _validate_source_binding(payload: Mapping[str, Any], context: ParserContext) -> None:
    if context.source_sha256 is not None:
        actual_source_sha256 = sha256_file(context.source_path)
        if actual_source_sha256 != context.source_sha256:
            raise ValueError(
                "PARSER_SOURCE_HASH_MISMATCH: "
                f"expected={context.source_sha256} actual={actual_source_sha256}"
            )

    declared_name = payload.get("file name")
    if declared_name is None:
        return
    if not isinstance(declared_name, str) or not declared_name.strip():
        raise ValueError("PARSER_SOURCE_FILENAME_INVALID: parser file name must be non-empty")
    if Path(declared_name).name == context.source_path.name:
        return
    if context.binding_authority == "SOURCE_BATCH_MANIFEST":
        return
    raise ValueError(
        "PARSER_SOURCE_FILENAME_MISMATCH: "
        "parser file name does not match source PDF basename"
    )


@dataclass(frozen=True, slots=True)
class OpenDataLoaderJsonAdapter:
    """Normalize one OpenDataLoader JSON artifact without document records."""

    kind: str = "OPENDATALOADER_JSON"

    def parse(self, context: ParserContext) -> NormalizedParserContribution:
        if context.options:
            unknown = ", ".join(sorted(context.options))
            raise ValueError(f"UNSUPPORTED_PARSER_OPTION: {unknown}")
        payload = read_parser_json(context.parser_artifact_path)
        _validate_source_binding(payload, context)
        raw_elements = load_raw_elements(
            context.parser_artifact_path,
            document_id="PARSER",
            revision_id="PARSER",
        )
        parsed_tables = load_parsed_tables(
            context.parser_artifact_path,
            document_id="PARSER",
            revision_id=(
                context.source_revision_id
                or context.source_sha256
                or sha256_file(context.source_path)
            ),
        )
        page_count = parser_page_count(payload, raw_elements)
        pdf_pages = read_pdf_page_geometries(context.source_path)
        dimensions = _reconcile_page_dimensions(payload, page_count, pdf_pages)
        geometry_by_page = {
            page.page_number: page for page in pdf_pages
        }
        page_counts: dict[int, int] = {}
        elements: list[ParsedElement] = []
        for raw in raw_elements:
            page_counts[raw.page_number] = page_counts.get(raw.page_number, 0) + 1
            index = page_counts[raw.page_number]
            bbox = parser_bbox(raw, geometry_by_page[raw.page_number])
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
            tables=parsed_tables,
            visuals=(),
            parser_artifact_sha256=sha256_file(context.parser_artifact_path),
            document_title=parser_document_title(payload, context.source_path.stem),
        )
