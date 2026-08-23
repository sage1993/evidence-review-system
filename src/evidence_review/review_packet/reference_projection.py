"""Safe presentation projection for page-bound reference evidence."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Literal, cast

from evidence_review.review_packet.reference_pages import build_reference_projection

ReferenceType = Literal[
    "TEXT",
    "TABLE",
    "PDF_PAGE",
    "IMAGE",
    "DIAGRAM",
    "DRAWING",
]

_MAX_TABLE_CELLS = 200
_MAX_CELL_TEXT = 1_000


def _reference_type(
    evidence_type: str,
    element_type: str | None,
    visual_kind: str | None,
) -> ReferenceType:
    normalized_evidence = evidence_type.strip().casefold()
    normalized_element = "" if element_type is None else element_type.strip().casefold()
    normalized_visual = "" if visual_kind is None else visual_kind.strip().casefold()
    if normalized_evidence == "table" or normalized_element == "table":
        return "TABLE"
    combined = " ".join((normalized_evidence, normalized_element, normalized_visual))
    if "drawing" in combined:
        return "DRAWING"
    if "diagram" in combined:
        return "DIAGRAM"
    if normalized_evidence == "visual" or normalized_element in {"figure", "image"}:
        return "IMAGE"
    if normalized_evidence in {"clause", "text"} or normalized_element in {
        "paragraph",
        "text",
    }:
        return "TEXT"
    return "PDF_PAGE"


def _mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        return None
    return cast(Mapping[str, object], value)


def _cell(value: object) -> dict[str, object] | None:
    source = _mapping(value)
    if source is None:
        return None
    row = source.get("row")
    column = source.get("column")
    text = source.get("text")
    row_span = source.get("row_span", 1)
    column_span = source.get("column_span", 1)
    selected = source.get("selected", False)
    if (
        isinstance(row, bool)
        or not isinstance(row, int)
        or row < 0
        or isinstance(column, bool)
        or not isinstance(column, int)
        or column < 0
        or not isinstance(text, str)
        or len(text) > _MAX_CELL_TEXT
        or isinstance(row_span, bool)
        or not isinstance(row_span, int)
        or row_span < 1
        or isinstance(column_span, bool)
        or not isinstance(column_span, int)
        or column_span < 1
        or not isinstance(selected, bool)
    ):
        return None
    return {
        "row": row,
        "column": column,
        "text": text,
        "row_span": row_span,
        "column_span": column_span,
        "selected": selected,
    }


def _table(raw_json: str | None) -> dict[str, object] | None:
    if raw_json is None:
        return None
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    source = _mapping(payload)
    if source is None:
        return None
    values = source.get("cells")
    if (
        isinstance(values, (str, bytes, bytearray))
        or not isinstance(values, Sequence)
        or not values
        or len(values) > _MAX_TABLE_CELLS
    ):
        return None
    cells = [_cell(value) for value in values]
    if any(cell is None for cell in cells):
        return None
    return {"cells": cast(list[dict[str, object]], cells)}


def project_reference_record(
    *,
    evidence_type: str,
    element_type: str | None,
    element_raw_json: str | None,
    table_raw_json: str | None,
    visual_kind: str | None,
) -> dict[str, object]:
    """Return allowlisted display metadata without exposing raw parser records."""
    reference_type = _reference_type(evidence_type, element_type, visual_kind)
    table_source = table_raw_json if table_raw_json is not None else element_raw_json
    return {
        "type": reference_type,
        "table": _table(table_source) if reference_type == "TABLE" else None,
        "visual": (
            {"kind": visual_kind}
            if reference_type in {"IMAGE", "DIAGRAM", "DRAWING"}
            and visual_kind is not None
            else None
        ),
    }


__all__ = ["build_reference_projection", "project_reference_record"]
