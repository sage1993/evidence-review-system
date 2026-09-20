# ruff: noqa: E501
"""Render the Issue #119 reference-subject-findings visual review workspace."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from html import escape
from typing import cast

from evidence_review.review_packet.quote_presentation import quote_preview, render_quote

_STATUS_META = {
    "mismatch": ("불일치", "mismatch"),
    "needs_check": ("확인 필요", "needs-check"),
    "not_comparable": ("대조 전", "not-comparable"),
    "match": ("일치", "match"),
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _raw_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _geometry(candidate: Mapping[str, object]) -> tuple[str, Sequence[object]]:
    geometry = _mapping(candidate.get("geometry"), "case_visual.geometry")
    if geometry.get("coordinate_system") != "IMAGE_TOP_LEFT_PIXELS":
        raise ValueError("case visual renderer requires IMAGE_TOP_LEFT_PIXELS")
    return str(geometry.get("type", "")), _sequence(
        geometry.get("coordinates"), "case_visual.geometry.coordinates"
    )


def _geometry_svg(candidate: Mapping[str, object]) -> str:
    """Render source-bound helper geometry with an explicit safe fill."""
    geometry_type, raw = _geometry(candidate)
    if geometry_type == "POINT":
        if len(raw) != 2:
            raise ValueError("POINT coordinates are invalid")
        return (
            '<circle class="case-visual-geometry" fill="none" '
            f'cx="{_number(raw[0], "point.x"):g}" '
            f'cy="{_number(raw[1], "point.y"):g}" r="8"/>'
        )
    if geometry_type == "BBOX":
        if len(raw) != 4:
            raise ValueError("BBOX coordinates are invalid")
        left, top, right, bottom = (
            _number(raw[index], "bbox.coordinate") for index in range(4)
        )
        return (
            '<rect class="case-visual-geometry" fill="none" '
            f'x="{left:g}" y="{top:g}" width="{right-left:g}" '
            f'height="{bottom-top:g}" rx="4" ry="4"/>'
        )
    if geometry_type in {"LINESTRING", "POLYGON"}:
        points: list[str] = []
        for item in raw:
            point = _sequence(item, "case_visual.geometry.point")
            if len(point) != 2:
                raise ValueError("path coordinates are invalid")
            points.append(
                f'{_number(point[0], "path.x"):g},{_number(point[1], "path.y"):g}'
            )
        if not points:
            raise ValueError("path coordinates are empty")
        tag = "polyline" if geometry_type == "LINESTRING" else "polygon"
        return (
            f'<{tag} class="case-visual-geometry" fill="none" '
            f'points="{" ".join(points)}"/>'
        )
    raise ValueError(f"unsupported case visual geometry: {geometry_type}")


def _anchor(candidate: Mapping[str, object]) -> tuple[float, float]:
    geometry_type, raw = _geometry(candidate)
    if geometry_type == "POINT" and len(raw) == 2:
        return _number(raw[0], "point.x"), _number(raw[1], "point.y")
    if geometry_type == "BBOX" and len(raw) == 4:
        left, top, right, bottom = (
            _number(raw[index], "bbox.coordinate") for index in range(4)
        )
        return (left + right) / 2, (top + bottom) / 2
    points: list[tuple[float, float]] = []
    for item in raw:
        point = _sequence(item, "case_visual.geometry.point")
        if len(point) == 2:
            points.append(
                (_number(point[0], "path.x"), _number(point[1], "path.y"))
            )
    if not points:
        raise ValueError("visual geometry has no focus point")
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def _geometry_bounds(candidate: Mapping[str, object]) -> tuple[float, float, float, float]:
    geometry_type, raw = _geometry(candidate)
    if geometry_type == "POINT":
        x, y = _anchor(candidate)
        return x - 8, y - 8, x + 8, y + 8
    if geometry_type == "BBOX" and len(raw) == 4:
        return tuple(_number(raw[index], "bbox.coordinate") for index in range(4))  # type: ignore[return-value]
    points = [
        (
            _number(_sequence(item, "geometry.point")[0], "geometry.x"),
            _number(_sequence(item, "geometry.point")[1], "geometry.y"),
        )
        for item in raw
    ]
    xs = [item[0] for item in points]
    ys = [item[1] for item in points]
    return min(xs), min(ys), max(xs), max(ys)


def _claim_index(model: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for index, item in enumerate(_sequence(model.get("claims", []), "claims")):
        claim = _mapping(item, f"claims[{index}]")
        claim_id = _raw_text(claim.get("claim_id"))
        if claim_id:
            result[claim_id] = claim
    return result


def _citation_cards(claim: Mapping[str, object]) -> tuple[list[str], list[str]]:
    cards: list[str] = []
    criteria: list[str] = []
    citations = _sequence(claim.get("citations", []), "claim.citations")
    for index, item in enumerate(citations):
        citation = _mapping(item, f"claim.citations[{index}]")
        quote = _raw_text(citation.get("quote"))
        if quote:
            criteria.append(quote)
        cards.append(
            "".join(
                (
                    '<article class="reference-card">',
                    '<div class="reference-source">',
                    f'<strong>{_text(citation.get("document_name") or citation.get("title") or "기준 근거")}</strong>',
                    f'<span>p.{_text(citation.get("page_number"))}</span></div>',
                    f'<blockquote>{_text(quote or claim.get("text"))}</blockquote>',
                    "</article>",
                )
            )
        )
    if not cards:
        claim_text = _raw_text(claim.get("text"))
        if claim_text:
            criteria.append(claim_text)
            cards.append(
                f'<article class="reference-card"><p>{_text(claim_text)}</p></article>'
            )
    return cards, criteria



def _legacy_references_for_finding(
    finding: Mapping[str, object],
    claims: Mapping[str, Mapping[str, object]],
) -> tuple[str, str]:
    direct_ids = [
        str(item)
        for item in _sequence(finding.get("direct_claim_ids", []), "finding.direct_claim_ids")
    ]
    related_ids = [
        str(item)
        for item in _sequence(finding.get("related_claim_ids", []), "finding.related_claim_ids")
    ]
    direct_cards: list[str] = []
    direct_criteria: list[str] = []
    for claim_id in direct_ids:
        claim = claims.get(claim_id)
        if claim is None:
            continue
        cards, criteria = _citation_cards(claim)
        direct_cards.extend(cards)
        direct_criteria.extend(criteria)

    related_cards: list[str] = []
    for claim_id in related_ids:
        claim = claims.get(claim_id)
        if claim is None:
            continue
        cards, _ = _citation_cards(claim)
        related_cards.extend(cards)

    parts: list[str] = []
    if direct_cards:
        parts.append(
            '<div class="direct-reference" data-direct-reference>'
            '<span class="reference-kind">직접 근거</span>'
            + "".join(direct_cards)
            + "</div>"
        )
    else:
        parts.append(
            '<div class="reference-empty" data-direct-reference-empty>'
            '<strong>직접 대조 가능한 기준을 찾지 못했습니다.</strong>'
            '<p>현재 자료만으로는 이 도면 요소를 법규·설계기준과 직접 비교할 수 없습니다.</p>'
            "</div>"
        )
    if related_cards:
        parts.append(
            '<div class="related-reference"><span class="reference-kind">관련 근거 '
            f'{len(related_cards)}건</span><div class="related-reference-list">'
            + "".join(related_cards)
            + "</div></div>"
        )
    elif not direct_cards:
        parts.append(
            '<p class="reference-related-empty">관련 근거도 연결되지 않았습니다.</p>'
        )
    criterion = direct_criteria[0] if direct_criteria else "직접 비교 가능한 기준 없음"
    return "".join(parts), quote_preview(criterion)


_REFERENCE_TYPE_LABELS = {
    "TEXT": "텍스트",
    "TABLE": "표",
    "PDF_PAGE": "PDF 페이지",
    "IMAGE": "이미지",
    "DIAGRAM": "다이어그램",
    "DRAWING": "도면",
}


def _reference_page_index(
    reference_pages: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for index, page in enumerate(reference_pages):
        asset_key = _raw_text(page.get("asset_key"))
        if not asset_key:
            raise ValueError(f"reference_pages[{index}].asset_key is required")
        if asset_key in result:
            raise ValueError(f"duplicate reference page asset key: {asset_key}")
        result[asset_key] = page
    return result


def _reference_anchor_bbox(
    anchor: Mapping[str, object],
    page: Mapping[str, object],
) -> tuple[float, float, float, float]:
    bbox = _mapping(anchor.get("bbox"), "reference.anchor.bbox")
    if bbox.get("coordinate_system") != "PDF_BOTTOM_LEFT_POINTS":
        raise ValueError(
            "reference anchor bbox requires PDF_BOTTOM_LEFT_POINTS coordinates"
        )
    raw_coordinates = _sequence(
        bbox.get("coordinates"), "reference.anchor.bbox.coordinates"
    )
    if len(raw_coordinates) != 4:
        raise ValueError("reference anchor bbox requires four coordinates")
    rotation = _number(page.get("rotation", 0), "reference_page.rotation")
    if rotation != 0:
        raise ValueError(
            "reference anchor rendering currently supports rotation=0 only"
        )
    left, bottom, right, top = (
        _number(raw_coordinates[index], "reference.anchor.bbox.coordinate")
        for index in range(4)
    )
    page_height = _number(page.get("height"), "reference_page.height")
    if right < left or top < bottom:
        raise ValueError("reference anchor bbox has invalid bounds")
    return left, page_height - top, right - left, top - bottom


def _reference_anchor_overlay(
    anchor: Mapping[str, object],
    page: Mapping[str, object],
) -> str:
    anchor_id = _raw_text(anchor.get("anchor_id"))
    if not anchor_id:
        raise ValueError("reference anchor anchor_id is required")
    x, y, width, height = _reference_anchor_bbox(anchor, page)
    page_width = _number(page.get("width"), "reference_page.width")
    page_height = _number(page.get("height"), "reference_page.height")
    return (
        f'<svg class="reference-overlay-layer" viewBox="0 0 {page_width:g} {page_height:g}" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
        '<rect class="reference-anchor-box" '
        f'data-reference-anchor="{_text(anchor_id)}" '
        f'x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}"/>'
        "</svg>"
    )


def _reference_raster_svg(page: Mapping[str, object]) -> str:
    width = _number(page.get("width"), "reference_page.width")
    height = _number(page.get("height"), "reference_page.height")
    return (
        f'<svg class="reference-raster-layer" viewBox="0 0 {width:g} {height:g}" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
        '<image data-reference-page-image data-reference-page-src="" '
        f'x="0" y="0" width="{width:g}" height="{height:g}" '
        'preserveAspectRatio="none"/>'
        "</svg>"
    )


def _reference_table(anchor: Mapping[str, object]) -> str:
    raw_table = anchor.get("table")
    if raw_table is None:
        return ""
    table = _mapping(raw_table, "reference.anchor.table")
    row_cells: dict[int, list[tuple[int, Mapping[str, object]]]] = {}
    for index, raw_cell in enumerate(
        _sequence(table.get("cells", []), "reference.anchor.table.cells")
    ):
        cell = _mapping(raw_cell, f"reference.anchor.table.cells[{index}]")
        row = int(_number(cell.get("row"), "reference.table.cell.row"))
        column = int(_number(cell.get("column"), "reference.table.cell.column"))
        row_cells.setdefault(row, []).append((column, cell))
    rows: list[str] = []
    for row in sorted(row_cells):
        cells: list[str] = []
        for _, cell in sorted(row_cells[row], key=lambda item: item[0]):
            row_span = int(_number(cell.get("row_span", 1), "reference.table.cell.row_span"))
            column_span = int(
                _number(cell.get("column_span", 1), "reference.table.cell.column_span")
            )
            class_name = (
                "reference-table-cell is-target"
                if cell.get("selected") is True
                else "reference-table-cell"
            )
            cells.append(
                f'<td class="{class_name}" data-table-cell="{row}:{int(_number(cell.get("column"), "reference.table.cell.column"))}" '
                f'rowspan="{row_span}" colspan="{column_span}">{_text(cell.get("text"))}</td>'
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return '<table class="reference-table"><tbody>' + "".join(rows) + "</tbody></table>"


def _reference_anchor_content(
    anchor: Mapping[str, object],
    page: Mapping[str, object],
    quote_override: str | None = None,
) -> tuple[str, str]:
    reference_type = _raw_text(anchor.get("type")).upper()
    label = _REFERENCE_TYPE_LABELS.get(reference_type)
    if label is None:
        raise ValueError(f"unsupported reference anchor type: {reference_type}")
    document_name = _raw_text(anchor.get("document_name")) or "기준 근거"
    page_number = anchor.get("page")
    title = _raw_text(anchor.get("title"))
    quote = quote_override or _raw_text(anchor.get("quote"))
    visual = anchor.get("visual")
    visual_kind = ""
    if isinstance(visual, Mapping):
        visual_kind = _raw_text(visual.get("kind"))
    metadata = (
        f'<div class="reference-anchor-source"><strong>{_text(document_name)}</strong>'
        f'<span>p.{_text(page_number)}</span></div>'
    )
    body: list[str] = [f'<span class="reference-type-label">{_text(label)}</span>']
    if title and reference_type != "TABLE":
        body.append(f"<h4>{_text(title)}</h4>")
    if quote:
        body.append(render_quote(quote))
    if reference_type in {"IMAGE", "DIAGRAM", "DRAWING"} and visual_kind:
        body.append(f'<p class="reference-visual-kind">{_text(visual_kind)}</p>')
    if reference_type == "PDF_PAGE" and not title and not quote:
        body.append('<p class="reference-page-only">페이지 전체 기준</p>')
    body_html = "".join(body)
    return metadata + f'<div class="reference-anchor-content">{body_html}</div>', reference_type


def _reference_anchor_card(
    anchor: Mapping[str, object],
    page: Mapping[str, object],
    role: str,
    quote_override: str | None = None,
) -> str:
    content, reference_type = _reference_anchor_content(anchor, page, quote_override)
    asset_key = _raw_text(page.get("asset_key"))
    image_sha256 = _raw_text(page.get("image_sha256"))
    width = _number(page.get("width"), "reference_page.width")
    height = _number(page.get("height"), "reference_page.height")
    return (
        f'<article class="reference-viewer-item" data-reference-type="{_text(reference_type)}" '
        f'data-reference-role="{_text(role)}">'
        f'<div class="reference-anchor-fixed">{content}</div>'
        '<div class="reference-controls">'
        '<button type="button" data-reference-expand aria-expanded="false">원문 크게 보기</button>'
        '<button type="button" data-reference-zoom="in" aria-label="기준 원문 확대">+</button>'
        '<button type="button" data-reference-zoom="out" aria-label="기준 원문 축소">−</button>'
        '<button type="button" data-reference-zoom="fit">기준 원문 맞춤</button>'
        '</div>'
        f'<div class="reference-page-stage" data-reference-page="{_text(asset_key)}" '
        f'data-reference-asset-key="{_text(asset_key)}" '
        f'data-reference-image-sha256="{_text(image_sha256)}" '
        f'data-page-width="{width:g}" data-page-height="{height:g}" '
        'data-reference-stage tabindex="0">'
        '<div class="reference-page-transform" data-reference-transform>'
        f"{_reference_raster_svg(page)}{_reference_anchor_overlay(anchor, page)}"
        "</div>"
        "</div></article>"
    )


def _related_reference_text_index(
    related_references: object,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for index, raw_reference in enumerate(
        _sequence(related_references, "case_visual_review.related_references")
    ):
        reference = _mapping(
            raw_reference, f"case_visual_review.related_references[{index}]"
        )
        citation = _mapping(
            reference.get("citation"),
            f"case_visual_review.related_references[{index}].citation",
        )
        citation_id = _raw_text(citation.get("citation_id"))
        text = _raw_text(reference.get("text"))
        if citation_id and text:
            result[citation_id] = text
    return result


def _typed_references_for_finding(
    finding: Mapping[str, object],
    reference_pages: Sequence[Mapping[str, object]],
    related_reference_texts: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    direct_anchors = [
        _mapping(item, f"finding.direct_reference_anchors[{index}]")
        for index, item in enumerate(
            _sequence(
                finding.get("direct_reference_anchors", []),
                "finding.direct_reference_anchors",
            )
        )
    ]
    related_anchors = [
        _mapping(item, f"finding.related_reference_anchors[{index}]")
        for index, item in enumerate(
            _sequence(
                finding.get("related_reference_anchors", []),
                "finding.related_reference_anchors",
            )
        )
    ]
    pages = _reference_page_index(reference_pages)
    related_texts = related_reference_texts or {}

    def render_group(
        anchors: Sequence[Mapping[str, object]],
        role: str,
    ) -> str:
        cards: list[str] = []
        for anchor in anchors:
            asset_key = _raw_text(anchor.get("page_asset_key"))
            page = pages.get(asset_key)
            if page is None:
                raise ValueError(f"reference page not found: {asset_key}")
            quote_override = (
                related_texts.get(_raw_text(anchor.get("anchor_id")))
                if role == "related"
                else None
            )
            cards.append(_reference_anchor_card(anchor, page, role, quote_override))
        return "".join(cards)

    parts: list[str] = []
    if direct_anchors:
        parts.append(
            '<div class="direct-reference" data-direct-reference>'
            '<span class="reference-kind">직접 근거</span>'
            + render_group(direct_anchors, "direct")
            + "</div>"
        )
    else:
        parts.append(
            '<div class="reference-empty" data-direct-reference-empty>'
            '<strong>직접 대조 가능한 기준을 찾지 못했습니다.</strong>'
            '<p>현재 자료만으로는 이 도면 요소를 법규·설계기준과 직접 비교할 수 없습니다.</p>'
            "</div>"
        )
    if related_anchors:
        parts.append(
            '<div class="related-reference"><span class="reference-kind">관련 근거 '
            f'{len(related_anchors)}건</span><div class="related-reference-list">'
            + render_group(related_anchors, "related")
            + "</div></div>"
        )
    elif not direct_anchors:
        parts.append(
            '<p class="reference-related-empty">관련 근거도 연결되지 않았습니다.</p>'
        )
    criterion = "직접 비교 가능한 기준 없음"
    if direct_anchors:
        first = direct_anchors[0]
        criterion = (
            _raw_text(first.get("quote"))
            or _raw_text(first.get("title"))
            or _raw_text(first.get("document_name"))
            or criterion
        )
    return "".join(parts), quote_preview(criterion)


def _references_for_finding(
    finding: Mapping[str, object],
    claims: Mapping[str, Mapping[str, object]],
    reference_pages: Sequence[Mapping[str, object]] | None = None,
    related_reference_texts: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    direct = _sequence(
        finding.get("direct_reference_anchors", []),
        "finding.direct_reference_anchors",
    )
    related = _sequence(
        finding.get("related_reference_anchors", []),
        "finding.related_reference_anchors",
    )
    if direct or related:
        return _typed_references_for_finding(
            finding, reference_pages or [], related_reference_texts
        )
    return _legacy_references_for_finding(finding, claims)


def _has_direct_reference(
    finding: Mapping[str, object],
    claims: Mapping[str, Mapping[str, object]],
) -> bool:
    """Return whether a finding has an actual direct comparison source."""
    direct_anchors = _sequence(
        finding.get("direct_reference_anchors", []),
        "finding.direct_reference_anchors",
    )
    related_anchors = _sequence(
        finding.get("related_reference_anchors", []),
        "finding.related_reference_anchors",
    )
    if direct_anchors or related_anchors:
        return bool(direct_anchors)
    return any(
        claim_id in claims and bool(_citation_cards(claims[claim_id])[0])
        for claim_id in (
            str(item)
            for item in _sequence(
                finding.get("direct_claim_ids", []), "finding.direct_claim_ids"
            )
        )
    )


def _has_related_reference(
    finding: Mapping[str, object],
    claims: Mapping[str, Mapping[str, object]],
) -> bool:
    """Return whether a finding has related reference content to present."""
    direct_anchors = _sequence(
        finding.get("direct_reference_anchors", []),
        "finding.direct_reference_anchors",
    )
    related_anchors = _sequence(
        finding.get("related_reference_anchors", []),
        "finding.related_reference_anchors",
    )
    if direct_anchors or related_anchors:
        return bool(related_anchors)
    return any(
        claim_id in claims and bool(_citation_cards(claims[claim_id])[0])
        for claim_id in (
            str(item)
            for item in _sequence(
                finding.get("related_claim_ids", []), "finding.related_claim_ids"
            )
        )
    )


def _fallback_findings(pages: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Keep older visual projections renderable while new projections supply findings."""
    findings: list[dict[str, object]] = []
    for page in pages:
        asset_key = _raw_text(page.get("asset_key"))
        candidates = _sequence(page.get("candidates", []), "page.candidates")
        for candidate in candidates:
            item = _mapping(candidate, "candidate")
            candidate_id = _raw_text(item.get("candidate_id"))
            value = (
                _raw_text(item.get("display_value"))
                or _raw_text(item.get("normalized_candidate"))
                or _raw_text(item.get("raw_value"))
                or "도면 확인사항"
            )
            direct_ids: list[str] = []
            related_ids: list[str] = []
            for raw_claim in _sequence(item.get("claims", []), "candidate.claims"):
                claim = _mapping(raw_claim, "candidate.claim")
                claim_id = _raw_text(claim.get("claim_id"))
                if not claim_id:
                    continue
                if claim.get("relation") == "direct" or (
                    "relation" not in claim and _sequence(item.get("review_statuses", []), "candidate.review_statuses")
                ):
                    direct_ids.append(claim_id)
                else:
                    related_ids.append(claim_id)
            tone = str(item.get("tone", "observation"))
            status = {
                "issue": "mismatch",
                "review": "needs_check",
                "compliant": "match",
                "observation": "not_comparable",
            }.get(tone, "not_comparable")
            findings.append(
                {
                    "finding_id": f"VF-{candidate_id or len(findings) + 1}",
                    "title": value,
                    "category": "visual_observation",
                    "status": status if direct_ids else "not_comparable",
                    "page_asset_key": asset_key,
                    "candidate_ids": [candidate_id] if candidate_id else [],
                    "issue_ids": list(_sequence(item.get("issue_ids", []), "candidate.issue_ids")),
                    "subject_value": value,
                    "focus_bbox": list(_geometry_bounds(item)),
                    "direct_claim_ids": direct_ids,
                    "related_claim_ids": related_ids,
                }
            )
    return findings


def _status_meta(status: str) -> tuple[str, str]:
    return _STATUS_META.get(status, _STATUS_META["not_comparable"])


def _icon(name: str) -> str:
    if name == "original-size":
        return (
            '<svg class="toolbar-icon" viewBox="0 0 24 24" aria-hidden="true">'
            '<text x="12" y="15" text-anchor="middle" fill="currentColor" '
            'font-family="ui-monospace,monospace" font-size="12" font-weight="700">1:1</text></svg>'
        )
    paths = {
        "prev": '<path d="M15 18l-6-6 6-6"/>',
        "next": '<path d="M9 18l6-6-6-6"/>',
        "plus": '<path d="M12 5v14M5 12h14"/>',
        "minus": '<path d="M5 12h14"/>',
        "fit-screen": '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>',
        "fit-width": '<path d="M4 7v10M20 7v10M7 12h10M7 12l3-3M7 12l3 3M17 12l-3-3M17 12l-3 3"/>',
        "decision": '<path d="M5 4h14v12H8l-3 3V4z"/><path d="M8 8h8M8 12h5"/>',
    }
    return (
        '<svg class="toolbar-icon" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{paths[name]}</g></svg>'
    )


def _strip_case_raster_payload(model: Mapping[str, object]) -> None:
    """Keep raster bytes in rendered asset nodes only; omit them from review-model JSON."""
    visual = model.get("case_visual_review")
    if not isinstance(visual, dict):
        return
    pages = visual.get("pages")
    if not isinstance(pages, list):
        return
    for page in pages:
        if not isinstance(page, dict):
            continue
        page.pop("data_uri", None)
        tiles = page.get("tiles")
        if isinstance(tiles, list):
            for tile in tiles:
                if isinstance(tile, dict):
                    tile.pop("data_uri", None)


def _page_raster_svg(page: Mapping[str, object], width: float, height: float) -> str:
    tiles = _sequence(page.get("tiles", []), "page.tiles")
    if tiles:
        images: list[str] = []
        for index, raw_tile in enumerate(tiles):
            tile = _mapping(raw_tile, f"page.tiles[{index}]")
            data_uri = _raw_text(tile.get("data_uri"))
            if not data_uri.startswith("data:image/"):
                raise ValueError("case visual tile data URI is missing")
            images.append(
                '<image data-case-tile '
                f'data-case-tile-src="{_text(data_uri)}" '
                f'data-tile-x="{_text(tile.get("x"))}" data-tile-y="{_text(tile.get("y"))}" '
                f'data-tile-width="{_text(tile.get("width"))}" data-tile-height="{_text(tile.get("height"))}" '
                f'x="{_text(tile.get("x"))}" y="{_text(tile.get("y"))}" '
                f'width="{_text(tile.get("width"))}" height="{_text(tile.get("height"))}" '
                'preserveAspectRatio="none"/>'
            )
        return (
            f'<svg class="case-raster-layer" viewBox="0 0 {width:g} {height:g}" '
            'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
            + "".join(images)
            + "</svg>"
        )
    data_uri = _raw_text(page.get("data_uri"))
    if not data_uri.startswith("data:image/"):
        raise ValueError("case visual raster data URI is missing")
    return (
        f'<svg class="case-raster-layer" viewBox="0 0 {width:g} {height:g}" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
        f'<image data-case-page-image data-case-page-src="{_text(data_uri)}" '
        f'x="0" y="0" width="{width:g}" height="{height:g}" preserveAspectRatio="none"/>'
        "</svg>"
    )


def _abstain_summary(model: Mapping[str, object]) -> str:
    status = str(model.get("status", model.get("display_status", ""))).upper()
    if status != "ABSTAIN":
        return ""
    reasons = [
        str(item).strip()
        for item in _sequence(model.get("abstention_reasons", []), "abstention_reasons")
        if str(item).strip()
    ]
    detail = reasons[0] if reasons else "직접 비교 가능한 기준 또는 필요한 전제가 부족합니다."
    return (
        '<section class="visual-abstain" role="status">'
        '<strong>현재 자료로 적합성 판정 불가</strong>'
        f'<span>{_text(detail)}</span></section>'
    )


def render_case_visual_review(model: Mapping[str, object]) -> str:
    """Render a reference ↔ subject ↔ semantic-findings workspace."""
    raw = model.get("case_visual_review")
    if raw is None:
        return ""
    visual = _mapping(raw, "case_visual_review")
    if visual.get("status") != "VISUAL_ANALYSIS_VALIDATED":
        raise ValueError("case visual review must be validated before rendering")
    pages = [
        _mapping(item, f"case_visual_review.pages[{index}]")
        for index, item in enumerate(
            _sequence(visual.get("pages", []), "case_visual_review.pages")
        )
    ]
    if not pages:
        raise ValueError("validated case visual review requires at least one page")
    reference_pages = [
        _mapping(item, f"case_visual_review.reference_pages[{index}]")
        for index, item in enumerate(
            _sequence(visual.get("reference_pages", []), "case_visual_review.reference_pages")
        )
    ]
    raw_findings = visual.get("findings")
    findings = (
        [
            _mapping(item, f"case_visual_review.findings[{index}]")
            for index, item in enumerate(_sequence(raw_findings, "case_visual_review.findings"))
        ]
        if raw_findings is not None
        else _fallback_findings(pages)
    )
    claims = _claim_index(model)
    related_reference_texts = _related_reference_text_index(
        visual.get("related_references", [])
    )

    candidate_finding_number: dict[str, int] = {}
    for number, finding in enumerate(findings, start=1):
        for candidate_id in _sequence(finding.get("candidate_ids", []), "finding.candidate_ids"):
            candidate_finding_number[str(candidate_id)] = number

    page_html: list[str] = []
    for page_index, page in enumerate(pages):
        asset_key = _raw_text(page.get("asset_key"))
        width = _number(page.get("width"), "case_visual_page.width")
        height = _number(page.get("height"), "case_visual_page.height")
        overlays: list[str] = []
        candidates = [
            _mapping(item, "case_visual_page.candidate")
            for item in _sequence(page.get("candidates", []), "case_visual_page.candidates")
        ]
        for candidate in candidates:
            candidate_id = _raw_text(candidate.get("candidate_id"))
            tone = str(candidate.get("tone", "observation"))
            x, y = _anchor(candidate)
            marker_number = candidate_finding_number.get(candidate_id, 0)
            overlays.append(
                "".join(
                    (
                        f'<g class="case-visual-overlay tone-{_text(tone)}" data-case-overlay="{_text(candidate_id)}">',
                        _geometry_svg(candidate),
                        f'<g class="case-visual-marker" transform="translate({x:g} {y:g})">',
                        '<circle class="marker-ring" r="13" fill="#fff"/>',
                        '<circle class="marker-core" r="10"/>',
                        f'<text class="marker-text" x="0" y="1">{marker_number or ""}</text>',
                        "</g></g>",
                    )
                )
            )
        page_html.append(
            "".join(
                (
                    f'<figure class="case-visual-page{" is-active" if page_index == 0 else ""}" '
                    f'data-case-page="{_text(asset_key)}" data-page-width="{width:g}" '
                    f'data-page-height="{height:g}"{"" if page_index == 0 else " hidden"}>',
                    '<div class="case-visual-stage" data-case-stage tabindex="0">',
                    '<div class="case-visual-transform" data-case-transform>',
                    _page_raster_svg(page, width, height),
                    f'<svg class="case-overlay-layer" viewBox="0 0 {width:g} {height:g}" '
                    'preserveAspectRatio="xMidYMid meet" aria-label="사용자 파일 검토 위치">'
                    + "".join(overlays)
                    + "</svg></div></div>",
                    f'<figcaption>{_text(page.get("document_name"))} · p.{_text(page.get("page"))}</figcaption>',
                    "</figure>",
                )
            )
        )

    reference_html: list[str] = []
    finding_html: list[str] = []
    status_counts = {key: 0 for key in _STATUS_META}
    any_direct = False
    for index, finding in enumerate(findings):
        finding_id = _raw_text(finding.get("finding_id")) or f"VF-{index + 1}"
        refs, criterion = _references_for_finding(
            finding, claims, reference_pages, related_reference_texts
        )
        has_direct = _has_direct_reference(finding, claims)
        any_direct = any_direct or has_direct
        reference_html.append(
            f'<section class="reference-focus{" is-active" if index == 0 else ""}" '
            f'data-case-reference="{_text(finding_id)}"{"" if index == 0 else " hidden"}>{refs}</section>'
        )
        status = str(finding.get("status", "not_comparable"))
        status_label, status_class = _status_meta(status)
        if not has_direct:
            status_label = "기준 연결 전"
        if status in status_counts:
            status_counts[status] += 1
        candidate_ids = [str(item) for item in _sequence(finding.get("candidate_ids", []), "finding.candidate_ids")]
        focus_bbox = [
            _number(value, "finding.focus_bbox")
            for value in _sequence(finding.get("focus_bbox", []), "finding.focus_bbox")
        ]
        if len(focus_bbox) != 4:
            raise ValueError("semantic visual finding requires a four-value focus_bbox")
        finding_html.append(
            "".join(
                (
                    f'<button class="finding-card status-{status_class}{" is-active" if index == 0 else ""}" '
                    f'type="button" data-case-finding="{_text(finding_id)}" '
                    f'data-finding-status="{_text(status)}" '
                    f'data-case-page-key="{_text(finding.get("page_asset_key"))}" '
                    f'data-case-candidate-ids="{_text("|".join(candidate_ids))}" '
                    f'data-case-focus-bbox="{_text(",".join(f"{value:g}" for value in focus_bbox))}">',
                    '<div class="finding-title-row">',
                    f'<span class="finding-number">{index + 1:02d}</span>',
                    f'<span class="finding-status">{_text(status_label)}</span></div>',
                    f'<h3>{_text(finding.get("title") or "도면 확인사항")}</h3>',
                    '<dl class="comparison-grid">',
                    (f'<div><dt>기준</dt><dd>{_text(criterion)}</dd></div>'
                     if has_direct else '<div><dt>기준 연결</dt><dd>아직 연결되지 않음</dd></div>'),
                    f'<div><dt>도면 관찰 내용</dt><dd>{_text(finding.get("subject_value"))}</dd></div>',
                    "</dl></button>",
                )
            )
        )

    if not findings:
        reference_html.append(
            '<section class="reference-focus is-active"><div class="reference-empty">'
            '<strong>직접 대조 가능한 기준을 찾지 못했습니다.</strong>'
            '<p>위치 기반 semantic Finding이 생성되지 않았습니다.</p></div></section>'
        )
        finding_html.append(
            '<div class="findings-empty"><strong>시각분석 완료</strong>'
            '<p>검토 가능한 위치 기반 Finding이 없습니다.</p></div>'
        )

    filters = [
        ("all", "전체", len(findings)),
        ("mismatch", "불일치", status_counts["mismatch"]),
        ("needs_check", "확인 필요", status_counts["needs_check"]),
        ("not_comparable", "대조 전", status_counts["not_comparable"]),
        ("match", "일치", status_counts["match"]),
    ]
    filter_html = "".join(
        f'<button type="button" class="finding-filter{" is-active" if key == "all" else ""}" '
        f'data-case-filter="{key}">{label} {count}</button>'
        for key, label, count in filters
    )
    initial_reference_width = 50
    _strip_case_raster_payload(model)
    return "".join(
        (
            '<section id="case-visual-review" class="visual-review-workspace" '
            f'data-overlay-mode="all" data-reference-available="{"true" if any_direct else "false"}" '
            'aria-label="기준 근거와 사용자 파일 대조 Workspace">',
            '<div class="visual-notices">',
            _abstain_summary(model),
            (
                ""
                if any_direct
                else '<p class="reference-unavailable" role="status">관련 자료 — 적용 기준 연결 전. 도면 관찰은 기준 대조 결과가 아닙니다.</p>'
            ),
            '</div>',
            '<div class="comparison-actions">'
            '<label><input type="checkbox" data-view-sync> 확대·이동 동기화</label>'
            '<button type="button" data-comparison-fullscreen>비교 화면 전체 보기</button>'
            '<button type="button" data-findings-toggle aria-expanded="true" '
            'aria-controls="visual-observations">관찰 목록 접기</button></div>',
            '<div class="workspace-grid">',
            f'<div class="comparison-workspace" data-case-split data-reference-width="{initial_reference_width}">',
            (
                '<section class="reference-viewer" aria-label="기준 근거 Viewer"><header>'
                '<strong>기준·관련 자료</strong><span>원문 위치</span></header><div class="reference-body">'
                + "".join(reference_html)
                + "</div></section>"
                + '<button class="viewer-divider" type="button" role="separator" '
                + 'aria-label="기준 근거와 사용자 파일 폭 조절" aria-orientation="vertical" '
                + f'aria-valuemin="26" aria-valuemax="70" aria-valuenow="{initial_reference_width}" '
                + 'data-case-divider><span></span></button>'
            ),
            '<section class="subject-viewer" aria-label="사용자 파일 Viewer">',
            '<header class="subject-toolbar"><div><strong>사용자 파일</strong><span>Subject</span></div>',
            '<div class="overlay-modes" role="group" aria-label="Annotation 표시">'
            '<button type="button" class="is-active" data-case-overlay-mode="all">전체 마커</button>'
            '<button type="button" data-case-overlay-mode="selected">선택 항목만</button></div>',
            '<div class="viewer-controls">',
            f'<button type="button" data-case-prev aria-label="이전 페이지">{_icon("prev")}</button>',
            f'<span><b data-case-page-number>1</b> / {len(pages)}</span>',
            f'<input type="number" min="1" max="{len(pages)}" value="1" '
            'data-case-page-jump aria-label="페이지 번호">',
            '<button type="button" data-case-page-go>이동</button>',
            f'<button type="button" data-case-next aria-label="다음 페이지">{_icon("next")}</button>',
            '<span class="control-separator"></span>',
            f'<button type="button" data-case-zoom-out aria-label="축소">{_icon("minus")}</button>',
            '<span data-case-zoom>100%</span>',
            f'<button type="button" data-case-zoom-in aria-label="확대">{_icon("plus")}</button>',
            f'<button type="button" data-case-fit-screen aria-label="화면 맞춤" title="화면 맞춤">{_icon("fit-screen")}</button>',
            f'<button type="button" data-case-fit-width aria-label="폭 맞춤" title="폭 맞춤">{_icon("fit-width")}</button>',
            f'<button type="button" data-case-original-size aria-label="원본 100%" title="원본 100%">{_icon("original-size")}</button>',
            '</div></header><div class="subject-body">',
            "".join(page_html),
            "</div></section></div>",
            '<aside id="visual-observations" class="findings-panel" aria-label="도면 관찰 항목"><header>'
            '<strong>도면 관찰 항목</strong><span>원문에서 추출 · 미확정 포함</span></header>',
            f'<div class="finding-filters">{filter_html}</div>',
            '<div class="findings-body">',
            "".join(finding_html),
            '<p class="findings-empty" data-findings-empty hidden>선택한 조건에 해당하는 관찰 항목이 없습니다.</p>',
            '</div></aside></div>',
            '<p class="case-visual-help">빨간 강조: 선택한 관찰 위치 · 위반 확정 표시가 아닙니다. '
            '마우스 휠 확대 · 드래그 이동 · 더블클릭 화면 맞춤</p>',
            "</section>",
        )
    )


def case_visual_css() -> str:
    """Return the shared CASE_VISUAL stylesheet for the document shell."""
    return (
        f"{CASE_VISUAL_CSS}{ISSUE_152_CASE_VISUAL_CSS}"
        .replace(
            "body[data-visual-decision-open=\"true\"] .case-decision-backdrop{display:block!important}",
            "",
        )
        .replace(
            ".case-decision-backdrop{position:fixed;inset:0;z-index:29;border:0;background:rgba(16,24,40,.22)}",
            "",
        )
        .replace(
            ".finding-pagination{display:flex;align-items:center;gap:8px;padding:6px 8px;border-top:1px solid var(--line);background:#f8fafc;font-size:10px}",
            "",
        )
        .replace(
            ".finding-pagination>button:not(.decision-open){width:28px;height:28px;border:1px solid #d0d5dd;border-radius:6px;background:#fff}",
            "",
        )
        .replace(
            ".decision-open{margin-left:auto;height:30px;padding:0 9px;border:1px solid #1570ef;border-radius:6px;background:#1570ef;color:#fff;display:flex;align-items:center;gap:4px;font-size:10px;font-weight:700}",
            "",
        )
        .replace("font-size:10.5px", "font-size:12px")
        .replace("font:600 10px", "font:600 12px")
        .replace("font-size:9px", "font-size:12px")
        .replace("font-size:10px", "font-size:12px")
        .replace("font-size:11px", "font-size:12px")
    )


CASE_VISUAL_CSS = r"""
#case-visual-review{--line:#d0d5dd;--muted:#667085;--panel:#fff;--canvas:#e9edf2;height:100%;min-height:0;background:#fff;overflow:hidden;display:grid;grid-template-rows:auto minmax(0,1fr) auto;position:relative}.visual-abstain{position:static;max-width:100%;display:flex;gap:8px;align-items:center;padding:7px 10px;border:1px solid #fedf89;border-radius:8px;background:rgba(255,250,235,.96);box-shadow:0 2px 8px rgba(16,24,40,.06);font-size:11px;color:#93370d}.visual-abstain strong{white-space:normal;color:#7a2e0e}.visual-abstain span{overflow-wrap:anywhere}.workspace-grid{min-height:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,326px)}.comparison-workspace{min-width:0;min-height:0;display:grid;grid-template-columns:var(--reference-width,42%) 10px minmax(0,1fr)}.reference-viewer,.subject-viewer,.findings-panel{min-width:0;min-height:0;background:var(--panel);display:grid}.reference-viewer,.subject-viewer{grid-template-rows:auto minmax(0,1fr)}.findings-panel{grid-template-rows:42px 38px minmax(0,1fr) 46px;border-left:1px solid var(--line)}.reference-viewer>header,.findings-panel>header,.subject-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 12px;border-bottom:1px solid var(--line);background:#f8fafc;font-size:12px}.reference-viewer header span,.findings-panel header span,.subject-toolbar span{font-size:10px;color:var(--muted)}.reference-body{min-height:0;overflow:hidden;padding:12px}.reference-focus{height:100%;overflow:auto;scrollbar-width:thin}.reference-kind{display:inline-flex;padding:3px 6px;border-radius:5px;background:#eef4ff;color:#3538cd;font-size:10px;font-weight:700;margin-bottom:7px}.reference-card{border:1px solid #e4e7ec;border-radius:9px;padding:12px;margin-bottom:9px;background:#fff}.reference-source{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:var(--muted)}.reference-source strong{color:#344054}.reference-card blockquote{margin:10px 0 0;padding:0;font-size:13px;line-height:1.65;color:#101828}.reference-empty{display:grid;place-content:center;min-height:58%;text-align:center;color:var(--muted);font-size:12px}.reference-empty strong{color:#344054;font-size:13px}.reference-empty p{max-width:320px;line-height:1.55}.reference-viewer-item{border:1px solid #e4e7ec;border-radius:9px;padding:10px;margin-bottom:9px;background:#fff}.reference-page-stage{position:relative;min-height:150px;padding:10px;border:1px solid #f2f4f7;border-radius:7px;background:#fcfcfd;overflow:hidden}.reference-anchor-source{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:var(--muted)}.reference-anchor-source strong{color:#344054}.reference-anchor-content{position:relative;z-index:1;padding-right:4px}.reference-type-label{display:inline-flex;margin:8px 0 2px;padding:3px 6px;border-radius:5px;background:#eef4ff;color:#3538cd;font-size:10px;font-weight:700}.reference-anchor-content h4{margin:5px 0;font-size:12px}.reference-anchor-content blockquote{margin:6px 0 0;padding:0;font-size:12px;line-height:1.55;color:#101828}.reference-visual-kind,.reference-page-only{margin:6px 0 0;color:var(--muted);font-size:10px}.reference-overlay-layer{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.reference-anchor-box{fill:rgba(46,144,250,.12);stroke:#2e90fa;stroke-width:2;vector-effect:non-scaling-stroke}.reference-table{width:100%;margin-top:8px;border-collapse:collapse;background:#fff;font-size:10px}.reference-table-cell{padding:5px 6px;border:1px solid #d0d5dd;text-align:left;color:#344054}.reference-table-cell.is-target{background:#fff4e5;box-shadow:inset 0 0 0 2px #f79009;color:#7a2e0e}.related-reference{margin-top:12px;border-top:1px solid #e4e7ec;padding-top:10px}.related-reference summary{cursor:pointer;color:#475467;font-size:11px;font-weight:700}.related-reference-list{margin-top:8px;opacity:.82}.reference-related-empty{text-align:center;color:#98a2b3;font-size:10px}.viewer-divider{padding:0;border:0;border-left:1px solid #e4e7ec;border-right:1px solid #e4e7ec;background:#f2f4f7;cursor:col-resize;display:grid;place-items:center}.viewer-divider span{width:3px;height:42px;border-radius:2px;background:#98a2b3}.viewer-divider:hover,.viewer-divider:focus-visible{background:#e4e7ec;outline:none}.subject-toolbar{display:flex;flex-wrap:wrap;padding:8px;gap:8px}.subject-toolbar>div:first-child{display:flex;align-items:baseline;gap:7px}.overlay-modes{display:flex;gap:4px}.overlay-modes button{height:27px;padding:0 7px;border:1px solid #d0d5dd;border-radius:6px;background:#fff;color:#475467;font-size:10px}.overlay-modes button.is-active{border-color:#84adff;background:#eff4ff;color:#175cd3}.viewer-controls{display:flex;flex-wrap:wrap;align-items:center;gap:5px}.viewer-controls button{width:28px;height:28px;border:1px solid #d0d5dd;border-radius:6px;background:#fff;display:grid;place-items:center;color:#344054}.toolbar-icon{width:15px;height:15px}.control-separator{width:1px;height:18px;background:#d0d5dd;margin:0 3px}.subject-body{position:relative;min-height:0;overflow:hidden;background:var(--canvas)}.case-visual-page{position:absolute;inset:0;margin:0;display:grid;grid-template-rows:minmax(0,1fr) 26px}.case-visual-stage{position:relative;overflow:hidden;cursor:grab;touch-action:none}.case-visual-stage.is-dragging{cursor:grabbing}.case-visual-transform{position:absolute;inset:0;transform-origin:0 0;will-change:transform}.case-raster-layer,.case-overlay-layer{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;user-select:none}.case-visual-page figcaption{display:grid;place-items:center;border-top:1px solid var(--line);background:#fff;color:var(--muted);font-size:10px}.case-visual-overlay{stroke-width:2.5;vector-effect:non-scaling-stroke}.case-visual-geometry{fill:none;stroke:currentColor;vector-effect:non-scaling-stroke}.case-visual-marker .marker-ring{stroke:#fff;stroke-width:4;vector-effect:non-scaling-stroke}.case-visual-marker .marker-core{fill:currentColor;stroke:#fff;stroke-width:1.5;vector-effect:non-scaling-stroke}.marker-text{fill:#fff;font-size:11px;font-weight:800;text-anchor:middle;dominant-baseline:central;stroke:none;pointer-events:none}.case-visual-overlay.tone-issue{color:#d92d20;stroke:#d92d20}.case-visual-overlay.tone-review{color:#f79009;stroke:#f79009}.case-visual-overlay.tone-observation{color:#2e90fa;stroke:#2e90fa}.case-visual-overlay.tone-compliant{color:#12b76a;stroke:#12b76a}.case-visual-overlay:not(.is-active) .case-visual-geometry{opacity:.18}.case-visual-overlay.is-active .case-visual-geometry{stroke-width:4;filter:drop-shadow(0 0 2px rgba(0,0,0,.18))}#case-visual-review[data-overlay-mode="selected"] .case-visual-overlay:not(.is-active){display:none}.finding-filters{display:flex;flex-wrap:wrap;align-items:center;gap:4px;padding:5px 7px;border-bottom:1px solid var(--line);background:#fbfcfe;overflow:hidden}.finding-filter{height:27px;padding:0 6px;border:1px solid #e4e7ec;border-radius:6px;background:#fff;color:#475467;font-size:10px;white-space:nowrap}.finding-filter.is-active{border-color:#84adff;background:#eff4ff;color:#175cd3}.findings-body{min-height:0;overflow:hidden;padding:8px;display:grid;grid-template-rows:repeat(3,minmax(0,1fr));gap:7px}.finding-card{min-height:min-content;overflow:visible;padding:9px;border:1px solid #e4e7ec;border-radius:9px;background:#fff;text-align:left;color:#101828}.finding-card:hover{background:#fcfcfd}.finding-card.is-active{border-color:#84adff;box-shadow:inset 3px 0 0 #2e90fa;background:linear-gradient(90deg,#eff8ff,#fff 72%)}.finding-title-row{display:flex;align-items:center;justify-content:space-between}.finding-number{font:600 10px ui-monospace,monospace;color:var(--muted)}.finding-status{font-size:10px;font-weight:700;padding:3px 6px;border-radius:999px}.status-mismatch .finding-status{color:#b42318;background:#fef3f2}.status-match .finding-status{color:#027a48;background:#ecfdf3}.status-needs-check .finding-status{color:#b54708;background:#fffaeb}.status-not-comparable .finding-status{color:#175cd3;background:#eff8ff}.finding-card h3{font-size:13px;margin:7px 0 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.comparison-grid{display:grid;gap:5px;margin:0}.comparison-grid div{padding:6px 7px;border-radius:6px;background:#f8fafc}.comparison-grid dt{font-size:9px;color:var(--muted);margin-bottom:2px}.comparison-grid dd{margin:0;font-size:10.5px;line-height:1.35;display:block;overflow-wrap:anywhere}.findings-empty{grid-row:1/-1;display:grid;place-content:center;text-align:center;color:var(--muted)}.finding-pagination{display:flex;align-items:center;gap:8px;padding:6px 8px;border-top:1px solid var(--line);background:#f8fafc;font-size:10px}.finding-pagination>button:not(.decision-open){width:28px;height:28px;border:1px solid #d0d5dd;border-radius:6px;background:#fff}.decision-open{margin-left:auto;height:30px;padding:0 9px;border:1px solid #1570ef;border-radius:6px;background:#1570ef;color:#fff;display:flex;align-items:center;gap:4px;font-size:10px;font-weight:700}.case-visual-help{margin:0;padding:6px 12px;border-top:1px solid #e4e7ec;color:var(--muted);font-size:10px;background:#fff;white-space:normal}.case-decision-backdrop{position:fixed;inset:0;z-index:29;border:0;background:rgba(16,24,40,.22)}body[data-visual-decision-open="true"] .case-decision-backdrop{display:block!important}@media(max-width:900px){.workspace-grid{grid-template-columns:minmax(0,1fr) 292px}.comparison-workspace{--reference-width:38%}.visual-abstain{max-width:48vw}}@media(max-width:720px){.workspace-grid{grid-template-columns:1fr}.findings-panel{position:static;width:100%;min-height:300px}.comparison-workspace{grid-template-columns:1fr}.reference-viewer{visibility:visible;min-height:360px}.viewer-divider{display:none}.visual-abstain{left:8px;top:6px;max-width:70vw}.subject-toolbar{grid-template-columns:auto 1fr}.overlay-modes{display:flex;flex-wrap:wrap}}
.reference-raster-layer,.reference-overlay-layer{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.reference-page-stage{cursor:grab;touch-action:none}.reference-page-stage.is-dragging{cursor:grabbing}.reference-page-transform{position:absolute;inset:0;transform-origin:0 0;will-change:transform}
.case-visual-page[hidden]{display:none!important}
"""


ISSUE_152_CASE_VISUAL_CSS = r"""

#case-visual-review[data-reference-available="false"] .reference-unavailable{position:static;margin:0;border:1px solid #b9cde8;border-radius:7px;padding:7px 10px;background:rgba(242,247,255,.96);color:#18365f;font-size:12px;line-height:1.4}
#case-visual-review[data-reference-available="false"] .related-reference-fallback{position:static;grid-row:3;max-width:100%;max-height:420px;overflow:auto;border:1px solid #b9cde8;border-radius:7px;padding:8px 10px;background:rgba(255,255,255,.96)}
#case-visual-review[data-reference-available="false"] .related-reference-fallback .reference-focus{height:auto;overflow:visible}
#case-visual-review[data-reference-available="false"] .related-reference-fallback .reference-empty{display:block;min-height:0;text-align:left}
#case-visual-review .viewer-controls button{width:40px;height:40px;min-height:0;display:inline-flex;align-items:center;justify-content:center;padding:0;line-height:0}
#case-visual-review .finding-filter{height:32px;min-height:0;padding:0 8px;font-size:12px}
#case-visual-review .findings-panel{grid-template-rows:auto auto minmax(0,1fr)}
#case-visual-review .findings-body{display:flex;flex-direction:column;overflow:auto}#case-visual-review .finding-card{flex:0 0 auto}
.case-visual-help{margin:0;padding:8px 12px;font-size:12px}
.toolbar-icon{display:block}
"""
__all__ = ["render_case_visual_review"]
