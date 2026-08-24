# ruff: noqa: E501
"""Render the Issue #119 reference-subject-findings visual review workspace."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from html import escape
from typing import cast


_FINDINGS_PER_PAGE = 3
_STATUS_META = {
    "mismatch": ("불일치", "mismatch"),
    "needs_check": ("확인 필요", "needs-check"),
    "not_comparable": ("비교 불가", "not-comparable"),
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


def _references_for_finding(
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
            '<details class="related-reference"><summary>관련 근거 '
            f'{len(related_cards)}건</summary><div class="related-reference-list">'
            + "".join(related_cards)
            + "</div></details>"
        )
    elif not direct_cards:
        parts.append(
            '<p class="reference-related-empty">관련 근거도 연결되지 않았습니다.</p>'
        )
    criterion = direct_criteria[0] if direct_criteria else "직접 비교 가능한 기준 없음"
    return "".join(parts), criterion


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
    paths = {
        "prev": '<path d="M15 18l-6-6 6-6"/>',
        "next": '<path d="M9 18l6-6-6-6"/>',
        "plus": '<path d="M12 5v14M5 12h14"/>',
        "minus": '<path d="M5 12h14"/>',
        "fit": '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>',
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
    status = str(model.get("display_status", model.get("status", ""))).upper()
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
        refs, criterion = _references_for_finding(finding, claims)
        direct_ids = _sequence(finding.get("direct_claim_ids", []), "finding.direct_claim_ids")
        any_direct = any_direct or bool(direct_ids)
        reference_html.append(
            f'<section class="reference-focus{" is-active" if index == 0 else ""}" '
            f'data-case-reference="{_text(finding_id)}"{"" if index == 0 else " hidden"}>{refs}</section>'
        )
        status = str(finding.get("status", "not_comparable"))
        status_label, status_class = _status_meta(status)
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
                    f'<div><dt>기준</dt><dd>{_text(criterion)}</dd></div>',
                    f'<div><dt>사용자 파일</dt><dd>{_text(finding.get("subject_value"))}</dd></div>',
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
        ("not_comparable", "비교 불가", status_counts["not_comparable"]),
        ("match", "일치", status_counts["match"]),
    ]
    filter_html = "".join(
        f'<button type="button" class="finding-filter{" is-active" if key == "all" else ""}" '
        f'data-case-filter="{key}">{label} {count}</button>'
        for key, label, count in filters
    )
    initial_reference_width = 42 if any_direct else 30
    total_pages = max(1, math.ceil(len(findings) / _FINDINGS_PER_PAGE))

    _strip_case_raster_payload(model)
    return "".join(
        (
            f"<style>{CASE_VISUAL_CSS}</style>",
            '<section id="case-visual-review" class="visual-review-workspace" '
            'data-overlay-mode="all" aria-label="기준 근거와 사용자 파일 대조 Workspace">',
            _abstain_summary(model),
            '<div class="workspace-grid">',
            f'<div class="comparison-workspace" data-case-split style="--reference-width:{initial_reference_width}%">',
            '<section class="reference-viewer" aria-label="기준 근거 Viewer"><header>'
            '<strong>기준 근거</strong><span>Reference</span></header><div class="reference-body">',
            "".join(reference_html),
            "</div></section>",
            f'<button class="viewer-divider" type="button" role="separator" '
            f'aria-label="기준 근거와 사용자 파일 폭 조절" aria-orientation="vertical" '
            f'aria-valuemin="26" aria-valuemax="70" aria-valuenow="{initial_reference_width}" '
            'data-case-divider><span></span></button>',
            '<section class="subject-viewer" aria-label="사용자 파일 Viewer">',
            '<header class="subject-toolbar"><div><strong>사용자 파일</strong><span>Subject</span></div>',
            '<div class="overlay-modes" role="group" aria-label="Annotation 표시">'
            '<button type="button" class="is-active" data-case-overlay-mode="all">전체 마커</button>'
            '<button type="button" data-case-overlay-mode="selected">선택 항목만</button></div>',
            '<div class="viewer-controls">',
            f'<button type="button" data-case-prev aria-label="이전 페이지">{_icon("prev")}</button>',
            f'<span><b data-case-page-number>1</b> / {len(pages)}</span>',
            f'<button type="button" data-case-next aria-label="다음 페이지">{_icon("next")}</button>',
            '<span class="control-separator"></span>',
            f'<button type="button" data-case-zoom-out aria-label="축소">{_icon("minus")}</button>',
            '<span data-case-zoom>100%</span>',
            f'<button type="button" data-case-zoom-in aria-label="확대">{_icon("plus")}</button>',
            f'<button type="button" data-case-reset aria-label="화면 맞춤">{_icon("fit")}</button>',
            '</div></header><div class="subject-body">',
            "".join(page_html),
            "</div></section></div>",
            '<aside class="findings-panel" aria-label="대조 결과"><header>'
            '<strong>대조 결과</strong><span>Findings</span></header>',
            f'<div class="finding-filters">{filter_html}</div>',
            '<div class="findings-body">',
            "".join(finding_html),
            '</div><footer class="finding-pagination">',
            '<button type="button" data-finding-prev aria-label="이전 결과 페이지">‹</button>',
            f'<span><b data-finding-page-number>1</b> / <b data-finding-page-total>{total_pages}</b></span>',
            '<button type="button" data-finding-next aria-label="다음 결과 페이지">›</button>',
            f'<button type="button" class="decision-open" data-case-decision-open>{_icon("decision")} 검토 판정</button>',
            '</footer></aside></div>',
            '<p class="case-visual-help">마우스 휠 Zoom · 좌클릭 Drag Pan · 더블클릭 Fit · 중앙 Divider 드래그로 Viewer 폭 조절</p>',
            '<button class="case-decision-backdrop" type="button" data-case-decision-backdrop '
            'aria-label="검토 판정 닫기" hidden></button>',
            f"<script>{CASE_VISUAL_SCRIPT}</script>",
            "</section>",
        )
    )


CASE_VISUAL_CSS = r"""
#case-visual-review{--line:#d0d5dd;--muted:#667085;--panel:#fff;--canvas:#e9edf2;height:100%;min-height:0;background:#fff;overflow:hidden;display:grid;grid-template-rows:minmax(0,1fr) 30px;position:relative}.visual-abstain{position:absolute;z-index:12;left:12px;top:10px;max-width:min(520px,42vw);display:flex;gap:8px;align-items:center;padding:7px 10px;border:1px solid #fedf89;border-radius:8px;background:rgba(255,250,235,.96);box-shadow:0 2px 8px rgba(16,24,40,.06);font-size:11px;color:#93370d}.visual-abstain strong{white-space:nowrap;color:#7a2e0e}.visual-abstain span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.workspace-grid{min-height:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,326px)}.comparison-workspace{min-width:0;min-height:0;display:grid;grid-template-columns:var(--reference-width,42%) 10px minmax(0,1fr)}.reference-viewer,.subject-viewer,.findings-panel{min-width:0;min-height:0;background:var(--panel);display:grid}.reference-viewer,.subject-viewer{grid-template-rows:42px minmax(0,1fr)}.findings-panel{grid-template-rows:42px 38px minmax(0,1fr) 46px;border-left:1px solid var(--line)}.reference-viewer>header,.findings-panel>header,.subject-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 12px;border-bottom:1px solid var(--line);background:#f8fafc;font-size:12px}.reference-viewer header span,.findings-panel header span,.subject-toolbar span{font-size:10px;color:var(--muted)}.reference-body{min-height:0;overflow:hidden;padding:12px}.reference-focus{height:100%;overflow:auto;scrollbar-width:thin}.reference-kind{display:inline-flex;padding:3px 6px;border-radius:5px;background:#eef4ff;color:#3538cd;font-size:10px;font-weight:700;margin-bottom:7px}.reference-card{border:1px solid #e4e7ec;border-radius:9px;padding:12px;margin-bottom:9px;background:#fff}.reference-source{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:var(--muted)}.reference-source strong{color:#344054}.reference-card blockquote{margin:10px 0 0;padding:0;font-size:13px;line-height:1.65;color:#101828}.reference-empty{display:grid;place-content:center;min-height:58%;text-align:center;color:var(--muted);font-size:12px}.reference-empty strong{color:#344054;font-size:13px}.reference-empty p{max-width:320px;line-height:1.55}.related-reference{margin-top:12px;border-top:1px solid #e4e7ec;padding-top:10px}.related-reference summary{cursor:pointer;color:#475467;font-size:11px;font-weight:700}.related-reference-list{margin-top:8px;opacity:.82}.reference-related-empty{text-align:center;color:#98a2b3;font-size:10px}.viewer-divider{padding:0;border:0;border-left:1px solid #e4e7ec;border-right:1px solid #e4e7ec;background:#f2f4f7;cursor:col-resize;display:grid;place-items:center}.viewer-divider span{width:3px;height:42px;border-radius:2px;background:#98a2b3}.viewer-divider:hover,.viewer-divider:focus-visible{background:#e4e7ec;outline:none}.subject-toolbar{display:grid;grid-template-columns:auto auto 1fr}.subject-toolbar>div:first-child{display:flex;align-items:baseline;gap:7px}.overlay-modes{display:flex;gap:4px}.overlay-modes button{height:27px;padding:0 7px;border:1px solid #d0d5dd;border-radius:6px;background:#fff;color:#475467;font-size:10px}.overlay-modes button.is-active{border-color:#84adff;background:#eff4ff;color:#175cd3}.viewer-controls{display:flex;align-items:center;justify-self:end;gap:5px}.viewer-controls button{width:28px;height:28px;border:1px solid #d0d5dd;border-radius:6px;background:#fff;display:grid;place-items:center;color:#344054}.toolbar-icon{width:15px;height:15px}.control-separator{width:1px;height:18px;background:#d0d5dd;margin:0 3px}.subject-body{position:relative;min-height:0;overflow:hidden;background:var(--canvas)}.case-visual-page{position:absolute;inset:0;margin:0;display:grid;grid-template-rows:minmax(0,1fr) 26px}.case-visual-stage{position:relative;overflow:hidden;cursor:grab;touch-action:none}.case-visual-stage.is-dragging{cursor:grabbing}.case-visual-transform{position:absolute;inset:0;transform-origin:0 0;will-change:transform}.case-raster-layer,.case-overlay-layer{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;user-select:none}.case-visual-page figcaption{display:grid;place-items:center;border-top:1px solid var(--line);background:#fff;color:var(--muted);font-size:10px}.case-visual-overlay{stroke-width:2.5;vector-effect:non-scaling-stroke}.case-visual-geometry{fill:none;stroke:currentColor;vector-effect:non-scaling-stroke}.case-visual-marker .marker-ring{stroke:#fff;stroke-width:4;vector-effect:non-scaling-stroke}.case-visual-marker .marker-core{fill:currentColor;stroke:#fff;stroke-width:1.5;vector-effect:non-scaling-stroke}.marker-text{fill:#fff;font-size:11px;font-weight:800;text-anchor:middle;dominant-baseline:central;stroke:none;pointer-events:none}.case-visual-overlay.tone-issue{color:#d92d20;stroke:#d92d20}.case-visual-overlay.tone-review{color:#f79009;stroke:#f79009}.case-visual-overlay.tone-observation{color:#2e90fa;stroke:#2e90fa}.case-visual-overlay.tone-compliant{color:#12b76a;stroke:#12b76a}.case-visual-overlay:not(.is-active) .case-visual-geometry{opacity:.18}.case-visual-overlay.is-active .case-visual-geometry{stroke-width:4;filter:drop-shadow(0 0 2px rgba(0,0,0,.18))}#case-visual-review[data-overlay-mode="selected"] .case-visual-overlay:not(.is-active){display:none}.finding-filters{display:flex;align-items:center;gap:4px;padding:5px 7px;border-bottom:1px solid var(--line);background:#fbfcfe;overflow:hidden}.finding-filter{height:27px;padding:0 6px;border:1px solid #e4e7ec;border-radius:6px;background:#fff;color:#475467;font-size:10px;white-space:nowrap}.finding-filter.is-active{border-color:#84adff;background:#eff4ff;color:#175cd3}.findings-body{min-height:0;overflow:hidden;padding:8px;display:grid;grid-template-rows:repeat(3,minmax(0,1fr));gap:7px}.finding-card{min-height:0;overflow:hidden;padding:9px;border:1px solid #e4e7ec;border-radius:9px;background:#fff;text-align:left;color:#101828}.finding-card:hover{background:#fcfcfd}.finding-card.is-active{border-color:#84adff;box-shadow:inset 3px 0 0 #2e90fa;background:linear-gradient(90deg,#eff8ff,#fff 72%)}.finding-title-row{display:flex;align-items:center;justify-content:space-between}.finding-number{font:600 10px ui-monospace,monospace;color:var(--muted)}.finding-status{font-size:10px;font-weight:700;padding:3px 6px;border-radius:999px}.status-mismatch .finding-status{color:#b42318;background:#fef3f2}.status-match .finding-status{color:#027a48;background:#ecfdf3}.status-needs-check .finding-status{color:#b54708;background:#fffaeb}.status-not-comparable .finding-status{color:#175cd3;background:#eff8ff}.finding-card h3{font-size:13px;margin:7px 0 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.comparison-grid{display:grid;gap:5px;margin:0}.comparison-grid div{padding:6px 7px;border-radius:6px;background:#f8fafc}.comparison-grid dt{font-size:9px;color:var(--muted);margin-bottom:2px}.comparison-grid dd{margin:0;font-size:10.5px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.findings-empty{grid-row:1/-1;display:grid;place-content:center;text-align:center;color:var(--muted)}.finding-pagination{display:flex;align-items:center;gap:8px;padding:6px 8px;border-top:1px solid var(--line);background:#f8fafc;font-size:10px}.finding-pagination>button:not(.decision-open){width:28px;height:28px;border:1px solid #d0d5dd;border-radius:6px;background:#fff}.decision-open{margin-left:auto;height:30px;padding:0 9px;border:1px solid #1570ef;border-radius:6px;background:#1570ef;color:#fff;display:flex;align-items:center;gap:4px;font-size:10px;font-weight:700}.case-visual-help{margin:0;padding:6px 12px;border-top:1px solid #e4e7ec;color:var(--muted);font-size:10px;background:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.case-decision-backdrop{position:fixed;inset:0;z-index:29;border:0;background:rgba(16,24,40,.22)}body[data-visual-decision-open="true"] .case-decision-backdrop{display:block!important}@media(max-width:900px){.workspace-grid{grid-template-columns:minmax(0,1fr) 292px}.comparison-workspace{--reference-width:38%}.visual-abstain{max-width:48vw}}@media(max-width:720px){.workspace-grid{grid-template-columns:1fr}.findings-panel{position:absolute;right:6px;top:46px;bottom:34px;width:min(86vw,310px);z-index:5;box-shadow:0 8px 28px rgba(16,24,40,.18)}.comparison-workspace{grid-template-columns:0 0 1fr}.reference-viewer,.viewer-divider{visibility:hidden}.visual-abstain{left:8px;top:6px;max-width:70vw}.subject-toolbar{grid-template-columns:auto 1fr}.overlay-modes{display:none}}
"""


CASE_VISUAL_SCRIPT = r"""
(()=>{const root=document.getElementById('case-visual-review');if(!root||root.dataset.bound==='1')return;root.dataset.bound='1';const pages=[...root.querySelectorAll('[data-case-page]')],cards=[...root.querySelectorAll('[data-case-finding]')],refs=[...root.querySelectorAll('[data-case-reference]')],overlays=[...root.querySelectorAll('[data-case-overlay]')],filterButtons=[...root.querySelectorAll('[data-case-filter]')];let pageIndex=0,activeCardIndex=cards.length?0:-1,filter='all',resultPage=0;const PAGE_SIZE=3,states=new WeakMap(),pageNo=root.querySelector('[data-case-page-number]'),zoomLabel=root.querySelector('[data-case-zoom]'),resultPageNo=root.querySelector('[data-finding-page-number]'),resultPageTotal=root.querySelector('[data-finding-page-total]');let tileFrame=0;function state(stage){let s=states.get(stage);if(!s){s={scale:1,x:0,y:0,drag:false,px:0,py:0};states.set(stage,s)}return s}function pageDimensions(page){return [Number(page?.dataset.pageWidth||0),Number(page?.dataset.pageHeight||0)]}function apply(stage){const s=state(stage),t=stage.querySelector('[data-case-transform]');if(t)t.style.transform=`translate(${s.x}px,${s.y}px) scale(${s.scale})`;if(zoomLabel&&pages[pageIndex]?.contains(stage))zoomLabel.textContent=`${Math.round(s.scale*100)}%`;scheduleVisibleTiles(pages[pageIndex])}function reset(stage){states.set(stage,{scale:1,x:0,y:0,drag:false,px:0,py:0});apply(stage)}function ensurePageRaster(page){if(!page)return;const full=page.querySelector('[data-case-page-image]');if(full&&!full.getAttribute('href'))full.setAttribute('href',full.dataset.casePageSrc||'');scheduleVisibleTiles(page)}function scheduleVisibleTiles(page){if(!page||tileFrame)return;tileFrame=requestAnimationFrame(()=>{tileFrame=0;ensureVisibleTiles(page)})}function ensureVisibleTiles(page){const stage=page?.querySelector('[data-case-stage]');if(!stage)return;const tiles=[...page.querySelectorAll('[data-case-tile]')];if(!tiles.length)return;const [pw,ph]=pageDimensions(page),rect=stage.getBoundingClientRect();if(!(pw>0&&ph>0&&rect.width>0&&rect.height>0))return;const fit=Math.min(rect.width/pw,rect.height/ph),ox=(rect.width-pw*fit)/2,oy=(rect.height-ph*fit)/2,s=state(stage),margin=Math.max(160,Math.min(rect.width,rect.height)*.25);tiles.forEach(tile=>{if(tile.getAttribute('href'))return;const x=Number(tile.dataset.tileX||0),y=Number(tile.dataset.tileY||0),w=Number(tile.dataset.tileWidth||0),h=Number(tile.dataset.tileHeight||0),left=s.x+(ox+x*fit)*s.scale,top=s.y+(oy+y*fit)*s.scale,right=left+w*fit*s.scale,bottom=top+h*fit*s.scale;if(right>=-margin&&bottom>=-margin&&left<=rect.width+margin&&top<=rect.height+margin)tile.setAttribute('href',tile.dataset.caseTileSrc||'')})}function showPage(key){const idx=pages.findIndex(p=>p.dataset.casePage===key);if(idx<0)return;pageIndex=idx;pages.forEach((p,i)=>{p.hidden=i!==idx;p.classList.toggle('is-active',i===idx)});if(pageNo)pageNo.textContent=String(idx+1);ensurePageRaster(pages[idx]);const stage=pages[idx].querySelector('[data-case-stage]');if(stage)apply(stage)}function candidateIds(card){return new Set((card?.dataset.caseCandidateIds||'').split('|').filter(Boolean))}function focusSubjectFinding(card){if(!card)return;showPage(card.dataset.casePageKey||'');requestAnimationFrame(()=>{const page=pages[pageIndex],stage=page?.querySelector('[data-case-stage]');if(!page||!stage)return;const bbox=(card.dataset.caseFocusBbox||'').split(',').map(Number);if(bbox.length!==4||bbox.some(v=>!Number.isFinite(v)))return;const [pw,ph]=pageDimensions(page),rect=stage.getBoundingClientRect();if(!(pw>0&&ph>0&&rect.width>0&&rect.height>0))return;const fit=Math.min(rect.width/pw,rect.height/ph),ox=(rect.width-pw*fit)/2,oy=(rect.height-ph*fit)/2,[l,t,r,b]=bbox,bw=Math.max(1,(r-l)*fit),bh=Math.max(1,(b-t)*fit),target=Math.min(5,Math.max(1,Math.min(rect.width*.58/bw,rect.height*.58/bh))),cx=ox+((l+r)/2)*fit,cy=oy+((t+b)/2)*fit,s=state(stage);s.scale=target;s.x=rect.width/2-cx*target;s.y=rect.height/2-cy*target;apply(stage)})}function activateCard(index,{focus=true}={}){if(index<0||index>=cards.length)return;activeCardIndex=index;const card=cards[index],id=card.dataset.caseFinding||'',ids=candidateIds(card);cards.forEach((item,i)=>item.classList.toggle('is-active',i===index));refs.forEach(ref=>{const on=ref.dataset.caseReference===id;ref.hidden=!on;ref.classList.toggle('is-active',on);if(on){const direct=ref.querySelector('[data-direct-reference], [data-direct-reference-empty]');direct?.scrollIntoView({block:'nearest'})}});overlays.forEach(overlay=>overlay.classList.toggle('is-active',ids.has(overlay.dataset.caseOverlay||'')));if(focus)focusSubjectFinding(card)}function filteredCardIndexes(){return cards.map((card,index)=>({card,index})).filter(({card})=>filter==='all'||card.dataset.findingStatus===filter).map(({index})=>index)}function renderResultPage({activate=true}={}){const indexes=filteredCardIndexes(),total=Math.max(1,Math.ceil(indexes.length/PAGE_SIZE));resultPage=Math.max(0,Math.min(resultPage,total-1));const slice=new Set(indexes.slice(resultPage*PAGE_SIZE,(resultPage+1)*PAGE_SIZE));cards.forEach((card,index)=>{card.hidden=!slice.has(index)});if(resultPageNo)resultPageNo.textContent=String(resultPage+1);if(resultPageTotal)resultPageTotal.textContent=String(total);if(activate&&indexes.length){const preferred=slice.has(activeCardIndex)?activeCardIndex:indexes[resultPage*PAGE_SIZE];activateCard(preferred,{focus:true})}}cards.forEach((card,index)=>card.addEventListener('click',()=>activateCard(index,{focus:true})));filterButtons.forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.caseFilter||'all';filterButtons.forEach(item=>item.classList.toggle('is-active',item===button));resultPage=0;renderResultPage({activate:true})}));root.querySelector('[data-finding-prev]')?.addEventListener('click',()=>{resultPage--;renderResultPage({activate:true})});root.querySelector('[data-finding-next]')?.addEventListener('click',()=>{resultPage++;renderResultPage({activate:true})});root.querySelector('[data-case-prev]')?.addEventListener('click',()=>showPage(pages[(pageIndex-1+pages.length)%pages.length]?.dataset.casePage||''));root.querySelector('[data-case-next]')?.addEventListener('click',()=>showPage(pages[(pageIndex+1)%pages.length]?.dataset.casePage||''));root.querySelectorAll('[data-case-overlay-mode]').forEach(button=>button.addEventListener('click',()=>{const mode=button.dataset.caseOverlayMode||'all';root.dataset.overlayMode=mode;root.querySelectorAll('[data-case-overlay-mode]').forEach(item=>item.classList.toggle('is-active',item===button))}));function zoom(factor,clientX,clientY){const stage=pages[pageIndex]?.querySelector('[data-case-stage]');if(!stage)return;const s=state(stage),rect=stage.getBoundingClientRect(),cx=clientX??rect.left+rect.width/2,cy=clientY??rect.top+rect.height/2,lx=(cx-rect.left-s.x)/s.scale,ly=(cy-rect.top-s.y)/s.scale,next=Math.min(5,Math.max(.5,s.scale*factor));s.x=cx-rect.left-lx*next;s.y=cy-rect.top-ly*next;s.scale=next;apply(stage)}root.querySelector('[data-case-zoom-in]')?.addEventListener('click',()=>zoom(1.2));root.querySelector('[data-case-zoom-out]')?.addEventListener('click',()=>zoom(.8333));root.querySelector('[data-case-reset]')?.addEventListener('click',()=>{const stage=pages[pageIndex]?.querySelector('[data-case-stage]');if(stage)reset(stage)});pages.forEach(page=>{const stage=page.querySelector('[data-case-stage]');if(!stage)return;stage.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.12:.89,e.clientX,e.clientY)},{passive:false});stage.addEventListener('dblclick',()=>reset(stage));stage.addEventListener('pointerdown',e=>{if(e.button!==0)return;const s=state(stage);s.drag=true;s.px=e.clientX;s.py=e.clientY;stage.setPointerCapture(e.pointerId);stage.classList.add('is-dragging')});stage.addEventListener('pointermove',e=>{const s=state(stage);if(!s.drag)return;s.x+=e.clientX-s.px;s.y+=e.clientY-s.py;s.px=e.clientX;s.py=e.clientY;apply(stage)});const stop=e=>{state(stage).drag=false;stage.classList.remove('is-dragging');try{stage.releasePointerCapture(e.pointerId)}catch(_){}};stage.addEventListener('pointerup',stop);stage.addEventListener('pointercancel',stop)});const split=root.querySelector('[data-case-split]'),divider=root.querySelector('[data-case-divider]');function setSplit(percent){if(!split||!divider)return;const value=Math.min(70,Math.max(26,percent));split.style.setProperty('--reference-width',`${value}%`);divider.setAttribute('aria-valuenow',String(Math.round(value)))}if(split&&divider){let dragging=false;divider.addEventListener('pointerdown',e=>{if(e.button!==0)return;dragging=true;divider.setPointerCapture(e.pointerId)});divider.addEventListener('pointermove',e=>{if(!dragging)return;const rect=split.getBoundingClientRect();setSplit((e.clientX-rect.left)/rect.width*100)});const stop=e=>{dragging=false;try{divider.releasePointerCapture(e.pointerId)}catch(_){}};divider.addEventListener('pointerup',stop);divider.addEventListener('pointercancel',stop);divider.addEventListener('dblclick',()=>setSplit(cards.some(card=>card.dataset.findingStatus!=='not_comparable')?42:30));divider.addEventListener('keydown',e=>{const now=Number(divider.getAttribute('aria-valuenow')||42);if(e.key==='ArrowLeft'){e.preventDefault();setSplit(now-2)}if(e.key==='ArrowRight'){e.preventDefault();setSplit(now+2)}})}function setDecision(open){document.body.dataset.visualDecisionOpen=open?'true':'false';const backdrop=root.querySelector('[data-case-decision-backdrop]');if(backdrop)backdrop.hidden=!open;const form=document.getElementById('decision-form');if(form){form.setAttribute('aria-hidden',open?'false':'true');if(open){let close=form.querySelector('[data-visual-decision-close]');if(!close){close=document.createElement('button');close.type='button';close.dataset.visualDecisionClose='';close.className='visual-decision-close';close.textContent='닫기';form.prepend(close);close.addEventListener('click',()=>setDecision(false))}form.querySelector('input,textarea,button')?.focus()}}}root.querySelector('[data-case-decision-open]')?.addEventListener('click',()=>setDecision(true));root.querySelector('[data-case-decision-backdrop]')?.addEventListener('click',()=>setDecision(false));document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.dataset.visualDecisionOpen==='true')setDecision(false)});showPage(pages[0]?.dataset.casePage||'');renderResultPage({activate:false});if(cards.length)activateCard(0,{focus:false})})();
"""


__all__ = ["render_case_visual_review"]
