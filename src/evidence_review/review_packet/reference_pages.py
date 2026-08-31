"""Materialize verified reference pages and citation anchors.

Only verified page identity, geometry, and image hash are projected. Raster
delivery belongs to the protected lazy-asset path.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from evidence_review.review_packet.page_image_verifier import (
    VerifiedPageImage,
    read_verified_page_image,
)

_GEOMETRY_TOLERANCE = 0.5


def _value(item: object, *names: str) -> object:
    if isinstance(item, Mapping):
        for name in names:
            if name in item:
                return item[name]
    else:
        for name in names:
            if hasattr(item, name):
                return getattr(item, name)
    raise KeyError(names[0])


def _text(item: object, *names: str) -> str:
    value = _value(item, *names)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing or invalid {names[0]}")
    return value


def _number(item: object, *names: str) -> float:
    value = _value(item, *names)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"missing or invalid {names[0]}")
    return float(value)


def _integer(item: object, *names: str) -> int:
    value = _value(item, *names)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"missing or invalid {names[0]}")
    return value


def _check_geometry(citation: Mapping[str, object], verified: object) -> None:
    checks = (
        ("page_width", ("pdf_width", "width", "page_width"), True),
        ("page_height", ("pdf_height", "height", "page_height"), True),
        ("page_origin_x", ("origin_x", "page_origin_x"), False),
        ("page_origin_y", ("origin_y", "page_origin_y"), False),
        ("page_rotation", ("rotation", "page_rotation"), False),
        ("page_box_kind", ("box_kind", "page_box_kind"), False),
    )
    for citation_name, verified_names, tolerant in checks:
        try:
            expected = citation[citation_name]
            actual = _value(verified, *verified_names)
        except KeyError as exc:
            raise ValueError("PAGE_RENDER_GEOMETRY_MISMATCH") from exc

        if tolerant:
            if (
                isinstance(expected, bool)
                or not isinstance(expected, (int, float))
                or not math.isfinite(float(expected))
                or isinstance(actual, bool)
                or not isinstance(actual, (int, float))
                or not math.isfinite(float(actual))
                or abs(float(expected) - float(actual)) > _GEOMETRY_TOLERANCE
            ):
                raise ValueError("PAGE_RENDER_GEOMETRY_MISMATCH")
        elif expected != actual:
            raise ValueError("PAGE_RENDER_GEOMETRY_MISMATCH")


def _bbox(citation: Mapping[str, object], verified: object) -> dict[str, object]:
    raw = citation.get("bbox")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 4:
        raise ValueError("citation bbox is outside the verified page bounds")

    try:
        coordinates = [float(value) for value in raw]
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("bbox contains a non-finite coordinate")
        width = _number(verified, "pdf_width", "width", "page_width")
        height = _number(verified, "pdf_height", "height", "page_height")
        origin_x = _number(verified, "origin_x", "page_origin_x")
        origin_y = _number(verified, "origin_y", "page_origin_y")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("citation bbox is outside the verified page bounds") from exc

    x1, y1, x2, y2 = coordinates
    if (
        x1 > x2
        or y1 > y2
        or x1 < origin_x
        or y1 < origin_y
        or x2 > origin_x + width
        or y2 > origin_y + height
    ):
        raise ValueError("citation bbox is outside the verified page bounds")

    return {
        "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
        "coordinates": coordinates,
    }


def _document_key(citation: Mapping[str, object]) -> tuple[str, str]:
    return (
        _text(citation, "document_id"),
        _text(citation, "revision_id"),
    )


def _page_key(citation: Mapping[str, object]) -> tuple[str, int, str]:
    return (
        _text(citation, "revision_id"),
        _integer(citation, "page_number", "page"),
        _text(citation, "source_hash"),
    )


def _page_projection(
    citation: Mapping[str, object],
    verified: object,
    asset_key: str,
) -> dict[str, object]:
    return {
        "asset_key": asset_key,
        "document_id": _text(citation, "document_id"),
        "revision_id": _text(citation, "revision_id"),
        "page": _integer(citation, "page_number", "page"),
        "source_hash": _text(citation, "source_hash"),
        "width": _number(verified, "pdf_width", "width", "page_width"),
        "height": _number(verified, "pdf_height", "height", "page_height"),
        "origin_x": _number(verified, "origin_x", "page_origin_x"),
        "origin_y": _number(verified, "origin_y", "page_origin_y"),
        "rotation": _integer(verified, "rotation", "page_rotation"),
        "box_kind": _text(verified, "box_kind", "page_box_kind"),
        "image_sha256": _text(verified, "image_sha256", "image_hash", "sha256"),
    }


def _presentation_fields(citation: Mapping[str, object]) -> tuple[object, object, object]:
    reference = citation.get("reference")
    if isinstance(reference, Mapping):
        return (
            reference.get("type"),
            reference.get("table"),
            reference.get("visual"),
        )
    return (
        citation.get("type"),
        citation.get("table"),
        citation.get("visual"),
    )


def build_reference_projection(
    citations: Sequence[Mapping[str, object]],
    *,
    page_root: Path,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, dict[str, object]],
]:
    """Build document, verified-page, and citation-anchor projections."""

    documents: list[dict[str, object]] = []
    pages: list[dict[str, object]] = []
    anchors: dict[str, dict[str, object]] = {}
    document_indexes: dict[tuple[str, str], int] = {}
    document_metadata: dict[tuple[str, str], tuple[object, object]] = {}
    page_indexes: dict[tuple[str, int, str], int] = {}
    page_documents: dict[tuple[str, int, str], str] = {}
    page_verified: dict[tuple[str, int, str], VerifiedPageImage] = {}

    for citation in citations:
        citation_id = _text(citation, "citation_id", "anchor_id")
        if citation_id in anchors:
            raise ValueError("duplicate reference citation id")

        document_key = _document_key(citation)
        metadata = (
            citation.get("document_name"),
            citation.get("document_page_count"),
        )
        prior_metadata = document_metadata.get(document_key)
        if prior_metadata is not None and prior_metadata != metadata:
            raise ValueError("conflicting document metadata")
        document_metadata[document_key] = metadata

        page_key = _page_key(citation)
        document_id = document_key[0]
        existing_document_id = page_documents.get(page_key)
        if existing_document_id is not None and existing_document_id != document_id:
            raise ValueError("reference page has conflicting document identity")

        verified = read_verified_page_image(
            page_root,
            page_key[0],
            page_key[1],
            page_key[2],
        )
        _check_geometry(citation, verified)
        _bbox(citation, verified)

        page_index = page_indexes.get(page_key)
        if page_index is None:
            page_index = len(pages)
            page_indexes[page_key] = page_index
            page_documents[page_key] = document_id
            page_verified[page_key] = verified
            pages.append(
                _page_projection(
                    citation,
                    verified,
                    f"reference-page-{page_index + 1}",
                )
            )
        else:
            verified = page_verified[page_key]

        asset_key = cast(str, pages[page_index]["asset_key"])
        if document_key not in document_indexes:
            document_indexes[document_key] = len(documents)
            documents.append(
                {
                    "document_id": document_key[0],
                    "revision_id": document_key[1],
                    "document_name": citation.get("document_name"),
                    "document_page_count": citation.get("document_page_count"),
                    "page_asset_keys": [],
                }
            )
        document = documents[document_indexes[document_key]]
        page_asset_keys = cast(list[str], document["page_asset_keys"])
        if asset_key not in page_asset_keys:
            page_asset_keys.append(asset_key)

        reference_type, table, visual = _presentation_fields(citation)
        anchors[citation_id] = {
            "anchor_id": citation_id,
            "type": reference_type,
            "document_id": document_key[0],
            "revision_id": document_key[1],
            "document_name": citation.get("document_name"),
            "page": page_key[1],
            "page_asset_key": asset_key,
            "title": citation.get("title"),
            "quote": citation.get("quote"),
            "bbox": _bbox(citation, verified),
            "table": table,
            "visual": visual,
        }

    return documents, pages, anchors
