"""Verified reference page and anchor materialization for visual review."""
from __future__ import annotations

import base64
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from evidence_review.review_packet.page_image_verifier import (
    VerifiedPageImage,
    read_verified_page_image,
)

_GEOMETRY_TOLERANCE = 0.5


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a string")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _bbox(value: object, page: VerifiedPageImage) -> list[float]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError("citation bbox must be an array")
    if len(value) != 4:
        raise ValueError("citation bbox must contain four values")
    left, bottom, right, top = (
        _number(item, "citation.bbox") for item in value
    )
    if (
        left < 0
        or bottom < 0
        or right < left
        or top < bottom
        or right > page.pdf_width
        or top > page.pdf_height
    ):
        raise ValueError("citation bbox is outside the verified page bounds")
    return [left, bottom, right, top]


def _verify_geometry(citation: Mapping[str, object], page: VerifiedPageImage) -> None:
    width = _number(citation.get("page_width"), "citation.page_width")
    height = _number(citation.get("page_height"), "citation.page_height")
    if (
        abs(width - page.pdf_width) > _GEOMETRY_TOLERANCE
        or abs(height - page.pdf_height) > _GEOMETRY_TOLERANCE
    ):
        raise ValueError(
            "PAGE_RENDER_GEOMETRY_MISMATCH: "
            f"citation={width}x{height} page_image={page.pdf_width}x{page.pdf_height}"
        )
    expected = (
        ("page_origin_x", page.origin_x),
        ("page_origin_y", page.origin_y),
        ("page_rotation", page.rotation),
        ("page_box_kind", page.box_kind),
    )
    for field, expected_value in expected:
        provided = citation.get(field)
        if provided is not None and provided != expected_value:
            raise ValueError(f"PAGE_RENDER_GEOMETRY_MISMATCH: {field}")


def build_reference_projection(
    citations: Sequence[Mapping[str, object]],
    *,
    page_root: Path,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, dict[str, object]],
]:
    """Materialize each cited page once and bind safe citation anchors to it."""
    documents: list[dict[str, object]] = []
    document_by_key: dict[tuple[str, str], dict[str, object]] = {}
    pages: list[dict[str, object]] = []
    page_by_key: dict[tuple[str, int, str], tuple[dict[str, object], VerifiedPageImage]] = {}
    anchors: dict[str, dict[str, object]] = {}

    for citation in citations:
        citation_id = _string(citation.get("citation_id"), "citation.citation_id")
        if citation_id in anchors:
            raise ValueError("duplicate reference citation id")
        document_id = _string(citation.get("document_id"), "citation.document_id")
        revision_id = _string(citation.get("revision_id"), "citation.revision_id")
        page_number = _positive_int(citation.get("page_number"), "citation.page_number")
        source_hash = _string(citation.get("source_hash"), "citation.source_hash")
        page_key = (revision_id, page_number, source_hash)
        existing_page = page_by_key.get(page_key)
        if existing_page is None:
            verified = read_verified_page_image(
                page_root,
                revision_id,
                page_number,
                source_hash,
            )
            _verify_geometry(citation, verified)
            page_document: dict[str, object] = {
                "asset_key": f"reference-page-{len(pages) + 1}",
                "document_id": document_id,
                "revision_id": revision_id,
                "page": page_number,
                "source_hash": source_hash,
                "width": verified.pdf_width,
                "height": verified.pdf_height,
                "origin_x": verified.origin_x,
                "origin_y": verified.origin_y,
                "rotation": verified.rotation,
                "box_kind": verified.box_kind,
                "image_sha256": verified.image_sha256,
                "data_uri": "data:image/png;base64,"
                + base64.b64encode(verified.image_bytes).decode("ascii"),
            }
            pages.append(page_document)
            page_by_key[page_key] = (page_document, verified)
        else:
            page_document, verified = existing_page
            if page_document["document_id"] != document_id:
                raise ValueError("reference page has conflicting document identity")
            _verify_geometry(citation, verified)

        document_key = (document_id, revision_id)
        document = document_by_key.get(document_key)
        document_name = str(citation.get("document_name") or citation.get("title") or document_id)
        page_count = _positive_int(
            citation.get("document_page_count"),
            "citation.document_page_count",
        )
        if document is None:
            document = {
                "document_id": document_id,
                "revision_id": revision_id,
                "document_name": document_name,
                "page_count": page_count,
                "page_asset_keys": [],
            }
            documents.append(document)
            document_by_key[document_key] = document
        elif (
            document["document_name"] != document_name
            or document["page_count"] != page_count
        ):
            raise ValueError("reference document metadata is inconsistent")
        asset_keys = cast(list[str], document["page_asset_keys"])
        asset_key = cast(str, page_document["asset_key"])
        if asset_key not in asset_keys:
            asset_keys.append(asset_key)

        reference = _mapping(citation.get("reference"), "citation.reference")
        bbox = _bbox(citation.get("bbox"), verified)
        anchors[citation_id] = {
            "anchor_id": citation_id,
            "type": _string(reference.get("type"), "citation.reference.type"),
            "document_id": document_id,
            "revision_id": revision_id,
            "document_name": document_name,
            "page": page_number,
            "page_asset_key": asset_key,
            "title": str(citation.get("title") or ""),
            "quote": str(citation.get("quote") or ""),
            "bbox": {
                "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
                "coordinates": bbox,
            },
            "table": reference.get("table"),
            "visual": reference.get("visual"),
        }

    return documents, pages, anchors


__all__ = ["build_reference_projection"]
