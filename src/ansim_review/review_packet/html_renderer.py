"""Self-contained, print-safe Review Workspace rendering."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import cast

_GEOMETRY_TOLERANCE = 0.5


@dataclass(frozen=True, slots=True)
class _PageAsset:
    data_uri: str
    pdf_width: float
    pdf_height: float
    rotation: int = 0


@dataclass(frozen=True, slots=True)
class _CitationRender:
    citation_id: str
    evidence_id: str
    metadata_html: str
    overlay_html: str


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


def _display_value(value: object) -> str:
    if isinstance(value, (Mapping, list, tuple)):
        return _text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return _text(value)


def _page_number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("citation page_number must be a positive integer")
    return value


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a positive number")
    result = float(value)
    if result <= 0 or result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be a positive number")
    return result


def _bbox(value: object) -> list[float]:
    items = _sequence(value, "bbox")
    if len(items) != 4:
        raise ValueError("citation bbox must have four values")
    result: list[float] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("citation bbox must contain numbers")
        number = float(item)
        if number != number or number in (float("inf"), float("-inf")):
            raise ValueError("citation bbox must contain finite numbers")
        result.append(number)
    left, bottom, right, top = result
    if left > right or bottom > top:
        raise ValueError("citation bbox coordinates are inverted")
    return result


def _verified_page_image(
    page_root: Path,
    revision_id: str,
    page_number: int,
    source_hash: str,
) -> _PageAsset:
    directory = page_root / revision_id
    stem = f"page-{page_number:04d}"
    image_path = directory / f"{stem}.png"
    metadata_path = directory / f"{stem}.json"
    if not image_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError(f"verified page image missing: {revision_id} page {page_number}")

    metadata = _mapping(
        json.loads(metadata_path.read_text(encoding="utf-8")),
        "page image metadata",
    )
    required = {
        "format",
        "version",
        "revision_id",
        "page_number",
        "source_hash",
        "pdf_width",
        "pdf_height",
        "image_sha256",
    }
    optional = {"origin_x", "origin_y", "rotation", "box_kind"}
    if not required.issubset(metadata) or set(metadata) - required - optional:
        raise ValueError("page image metadata fields are invalid")
    if metadata.get("format") != "ansim/page-image" or metadata.get("version") != 1:
        raise ValueError("unsupported page image metadata")
    if metadata.get("revision_id") != revision_id:
        raise ValueError("page image revision mismatch")
    if metadata.get("page_number") != page_number:
        raise ValueError("page image page number mismatch")
    if metadata.get("source_hash") != source_hash:
        raise ValueError("page image source hash mismatch")

    image_hash = metadata.get("image_sha256")
    if not isinstance(image_hash, str) or len(image_hash) != 64:
        raise ValueError("page image hash is invalid")
    image_bytes = image_path.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != image_hash:
        raise ValueError("page image hash mismatch")

    pdf_width = _positive_number(metadata.get("pdf_width"), "pdf_width")
    pdf_height = _positive_number(metadata.get("pdf_height"), "pdf_height")
    rotation = metadata.get("rotation", 0)
    if (
        isinstance(rotation, bool)
        or not isinstance(rotation, int)
        or rotation not in {0, 90, 180, 270}
    ):
        raise ValueError("page image rotation is invalid")
    return _PageAsset(
        data_uri="data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii"),
        pdf_width=pdf_width,
        pdf_height=pdf_height,
        rotation=rotation,
    )


def _verify_page_geometry(
    citation: Mapping[str, object],
    page_asset: _PageAsset,
) -> None:
    width = _positive_number(citation.get("page_width"), "citation.page_width")
    height = _positive_number(citation.get("page_height"), "citation.page_height")
    if (
        abs(width - page_asset.pdf_width) > _GEOMETRY_TOLERANCE
        or abs(height - page_asset.pdf_height) > _GEOMETRY_TOLERANCE
    ):
        raise ValueError(
            "PAGE_RENDER_GEOMETRY_MISMATCH: "
            f"citation={width}x{height} "
            f"page_image={page_asset.pdf_width}x{page_asset.pdf_height}"
        )


def _citation_identity(citation: Mapping[str, object]) -> tuple[str, int, str]:
    return (
        str(citation.get("revision_id", "")),
        _page_number(citation.get("page_number")),
        str(citation.get("source_hash", "")),
    )


def _page_assets(
    claims: Sequence[object], page_root: Path
) -> dict[tuple[str, int, str], tuple[str, _PageAsset]]:
    """Read each cited page once and verify every citation against its geometry."""
    assets: dict[tuple[str, int, str], tuple[str, _PageAsset]] = {}
    for claim_value in claims:
        claim = _mapping(claim_value, "claim")
        for citation_value in _sequence(claim.get("citations", []), "citations"):
            citation = _mapping(citation_value, "citation")
            identity = _citation_identity(citation)
            if identity not in assets:
                revision_id, page_number, source_hash = identity
                page_asset = _verified_page_image(
                    page_root,
                    revision_id,
                    page_number,
                    source_hash,
                )
                _verify_page_geometry(citation, page_asset)
                assets[identity] = (f"page-{len(assets) + 1}", page_asset)
            else:
                _, page_asset = assets[identity]
                _verify_page_geometry(citation, page_asset)
    return assets


def _citation_render(
    value: object,
    *,
    asset_key: str,
    page_asset: _PageAsset,
) -> _CitationRender:
    citation = _mapping(value, "citation")
    revision_id, page_number, source_hash = _citation_identity(citation)
    left, bottom, right, top = _bbox(citation.get("bbox", []))
    if left < 0 or bottom < 0 or right > page_asset.pdf_width or top > page_asset.pdf_height:
        raise ValueError("citation bbox is outside the verified page bounds")
    if page_asset.rotation == 0:
        viewport_width, viewport_height = page_asset.pdf_width, page_asset.pdf_height
        rect_x, rect_y = left, page_asset.pdf_height - top
        rect_width, rect_height = right - left, top - bottom
    elif page_asset.rotation == 90:
        viewport_width, viewport_height = page_asset.pdf_height, page_asset.pdf_width
        rect_x, rect_y = bottom, left
        rect_width, rect_height = top - bottom, right - left
    elif page_asset.rotation == 180:
        viewport_width, viewport_height = page_asset.pdf_width, page_asset.pdf_height
        rect_x, rect_y = page_asset.pdf_width - right, bottom
        rect_width, rect_height = right - left, top - bottom
    else:
        viewport_width, viewport_height = page_asset.pdf_height, page_asset.pdf_width
        rect_x, rect_y = page_asset.pdf_height - top, page_asset.pdf_width - right
        rect_width, rect_height = top - bottom, right - left
    bbox_text = ",".join(str(item) for item in (left, bottom, right, top))
    citation_id = str(citation.get("citation_id", ""))
    evidence_id = str(citation.get("evidence_id", ""))
    metadata_html = "".join(
        (
            '<article class="citation" ',
            f'data-asset-key="{_text(asset_key)}" ',
            f'data-citation-id="{_text(citation_id)}" ',
            f'data-evidence-id="{_text(evidence_id)}" ',
            f'data-bbox="{_text(bbox_text)}">',
            f"<h4>{_text(citation.get('title'))}</h4>",
            '<p class="citation-location"><strong>',
            f"{_text(citation.get('document_id'))} · page {page_number}</strong></p>",
            f"<p>개정 {_text(revision_id)}</p>",
            f"<blockquote>{_text(citation.get('quote'))}</blockquote>",
            '<dl class="provenance">',
            f"<dt>인용 ID</dt><dd><code>{_text(citation_id)}</code></dd>",
            f"<dt>근거 ID</dt><dd><code>{_text(evidence_id)}</code></dd>",
            f"<dt>요소</dt><dd>{_text(citation.get('evidence_type'))}</dd>",
            f"<dt>좌표</dt><dd><code>{_text(bbox_text)}</code></dd>",
            f"<dt>형상</dt><dd><code>{_display_value(citation.get('geometry', bbox_text))}"
            "</code></dd>",
            f"<dt>원본 SHA-256</dt><dd><code>{_text(source_hash)}</code></dd>",
            "</dl>",
            '<button class="evidence-link" type="button" ',
            f'data-asset-key="{_text(asset_key)}" ',
            f'data-evidence-id="{_text(evidence_id)}">인용 위치 보기</button>',
            "</article>",
        )
    )
    overlay_html = "".join(
        (
            f'<svg viewBox="0 0 {viewport_width} {viewport_height}" ',
            'class="citation-overlay" ',
            f'data-asset-key="{_text(asset_key)}" ',
            f'data-citation-id="{_text(citation_id)}" ',
            f'data-evidence-id="{_text(evidence_id)}" ',
            'preserveAspectRatio="none" aria-label="citation bbox overlay">',
            f'<rect x="{rect_x}" y="{rect_y}" width="{rect_width}" ',
            f'height="{rect_height}"></rect>',
            "</svg>",
        )
    )
    return _CitationRender(
        citation_id=citation_id,
        evidence_id=evidence_id,
        metadata_html=metadata_html,
        overlay_html=overlay_html,
    )


def _table_rows(items: Sequence[object], columns: tuple[str, ...]) -> str:
    rows: list[str] = []
    for item in items:
        row = _mapping(item, "table row")
        cells = "".join(f"<td>{_display_value(row.get(column))}</td>" for column in columns)
        rows.append("<tr>" + cells + "</tr>")
    return "".join(rows) or f'<tr><td colspan="{len(columns)}">연결된 기록 없음</td></tr>'


def _string_set(value: object, field: str) -> set[str]:
    values: set[str] = set()
    for index, item in enumerate(_sequence(value, field)):
        if not isinstance(item, str):
            raise ValueError(f"{field}[{index}] must be a string")
        values.add(item)
    return values


def _record_cards(items: Sequence[object], empty_message: str) -> str:
    cards: list[str] = []
    for item in items:
        record = _mapping(item, "record")
        facts = "".join(
            f"<dt>{_text(name)}</dt><dd>{_display_value(value)}</dd>"
            for name, value in record.items()
        )
        cards.append(f'<dl class="record-card">{facts}</dl>')
    return "".join(cards) or f'<p class="empty-state">{_text(empty_message)}</p>'


def _value_list(values: Sequence[object], empty_message: str) -> str:
    entries = "".join(f"<li><code>{_text(value)}</code></li>" for value in values)
    return f"<ul>{entries}</ul>" if entries else f'<p class="empty-state">{empty_message}</p>'


def _review_items(
    model: Mapping[str, object], claims: Sequence[object]
) -> list[Mapping[str, object]]:
    values = _sequence(model.get("review_items", []), "review_items")
    if values:
        return [_mapping(value, "review_item") for value in values]
    return [
        {
            "item_id": f"ITEM-{claim.get('claim_id', '')}",
            "claim_id": claim.get("claim_id"),
            "status": "NOT_EVALUATED",
            "completeness": "UNKNOWN",
        }
        for claim in (_mapping(value, "claim") for value in claims)
    ]


def _render_status_band(model: Mapping[str, object]) -> str:
    display_status = model.get("display_status", model.get("status"))
    return "".join(
        (
            '<header id="review-status" class="status-band">',
            '<div class="status-copy"><div class="status-line">',
            f'<span class="status-pill" data-display-status>{_text(display_status)}</span>',
            f'<code>{_text(model.get("run_id"))}</code></div>',
            '<h1>근거 검토 화면</h1>',
            f'<p class="question-context">{_text(model.get("question"))}</p></div>',
            '<div class="header-actions"><button type="button" data-print>HTML 인쇄</button></div>',
            '<p class="warning">기계 평가는 최종 판정이 아닙니다.</p>',
            "</header>",
        )
    )


def _render_summary(model: Mapping[str, object]) -> str:
    display_status = model.get("display_status", model.get("status"))
    summary = _mapping(model.get("summary", {}), "summary")
    audit = _mapping(model.get("audit", {}), "audit")
    return "".join(
        (
            '<section id="review-summary" aria-labelledby="summary-heading">',
            '<div class="section-heading"><h2 id="summary-heading">검토 요약</h2>',
            '<p>서버가 검증한 패킷 지표</p></div>',
            '<dl class="metrics">',
            '<div class="metric"><dt>인용 근거</dt>',
            f'<dd>{_display_value(summary.get("citation_count"))}</dd>',
            f'<small>인용되지 않은 주장 {_display_value(audit.get("uncited_count"))}</small></div>',
            '<div class="metric"><dt>승인 규칙</dt>',
            f'<dd>{_display_value(summary.get("approved_rule_count"))}</dd>',
            f'<small>누락 입력 {_display_value(summary.get("missing_input_count"))}</small></div>',
            '<div class="metric"><dt>계산 결과</dt>',
            f'<dd>{_display_value(summary.get("calculation_count"))}</dd>',
            f'<small>충돌 {_display_value(summary.get("conflict_count"))}</small></div>',
            '<div class="metric" id="ready-for-review"><dt>현재 상태</dt>',
            f'<dd class="status-metric" data-display-status>{_text(display_status)}</dd>',
            f'<small>신뢰도 {_display_value(summary.get("confidence_score"))} · '
            f'{_display_value(summary.get("confidence_level"))}</small></div>',
            "</dl>",
            "</section>",
        )
    )


def _render_review_items(items: Sequence[Mapping[str, object]]) -> str:
    buttons: list[str] = []
    for index, item in enumerate(items):
        item_id = _text(item.get("item_id"))
        buttons.append(
            "".join(
                (
                    '<button class="review-item',
                    " is-selected" if index == 0 else "",
                    '" type="button" ',
                    f'data-item-id="{item_id}" aria-pressed="',
                    "true" if index == 0 else "false",
                    '"><span class="item-id">',
                    item_id,
                    "</span><span>",
                    _text(item.get("claim_id")),
                    "</span><span>",
                    _text(item.get("status")),
                    " · ",
                    _text(item.get("completeness")),
                    "</span></button>",
                )
            )
        )
    return "".join(
        (
            '<nav id="review-items" aria-label="검토 항목">',
            '<div class="panel-heading"><h2>검토 항목</h2>',
            f'<span>{len(items)}개 항목</span></div>',
            '<div class="review-item-list">',
            "".join(buttons) or '<p class="empty-state">검토 항목 없음</p>',
            "</div>",
            "</nav>",
        )
    )


def _render_evidence_viewer(
    assets: Mapping[tuple[str, int, str], tuple[str, _PageAsset]],
    overlays: Mapping[str, Sequence[str]],
) -> str:
    pages: list[str] = []
    for index, ((revision_id, page_number, source_hash), (asset_key, asset)) in enumerate(
        assets.items()
    ):
        pages.append(
            "".join(
                (
                    '<figure class="evidence-page',
                    " is-active" if index == 0 else "",
                    f'" id="evidence-{asset_key}" data-asset-key="{asset_key}" tabindex="-1">',
                    '<div class="page-stage"><div class="page-canvas">',
                    f'<img alt="검증된 원본 페이지 {page_number}" src="{asset.data_uri}">',
                    '<div class="overlay-layer">',
                    "".join(overlays.get(asset_key, [])),
                    "</div>",
                    "</div></div>",
                    '<figcaption><span><small>개정</small><strong>',
                    _text(revision_id),
                    '</strong></span><span><small>페이지</small><strong>',
                    str(page_number),
                    '</strong></span><span><small>source SHA-256</small><code>',
                    _text(source_hash),
                    "</code></span></figcaption></figure>",
                )
            )
        )
    return "".join(
        (
            '<section id="evidence-viewer" aria-labelledby="evidence-heading">',
            '<div class="viewer-heading"><div><h2 id="evidence-heading">근거 뷰어</h2>',
            '<p>검증된 페이지 원본과 인용 좌표</p></div>',
            '<div class="viewer-controls" aria-label="근거 표시 모드">',
            '<button type="button" data-viewer-mode="original" aria-pressed="false">원본</button>',
            '<button type="button" data-viewer-mode="evidence" aria-pressed="false">검출</button>',
            '<button type="button" data-viewer-mode="compare" aria-pressed="true">비교</button>',
            '<label>확대 <input id="evidence-zoom" type="range" min="1" max="2" '
            'step="0.1" value="1"></label></div></div>',
            "".join(pages) or '<p class="empty-state">검증된 인용 페이지 없음</p>',
            "</section>",
        )
    )


def _claim_for_item(
    item: Mapping[str, object], claims: Sequence[Mapping[str, object]]
) -> Mapping[str, object] | None:
    claim_id = item.get("claim_id")
    return next((claim for claim in claims if claim.get("claim_id") == claim_id), None)


def _render_detail_tabs(
    *,
    items: Sequence[Mapping[str, object]],
    claims: Sequence[Mapping[str, object]],
    citations: Mapping[str, Sequence[_CitationRender]],
    calculations: Sequence[object],
    rules: Sequence[object],
    audit: Mapping[str, object],
    exceptions: Sequence[object],
    conflicts: Sequence[object],
) -> str:
    panels: list[str] = []
    audit_records = _sequence(audit.get("records", []), "audit.records")
    global_exceptions = {str(value): value for value in exceptions}
    global_conflicts = {str(value): value for value in conflicts}
    for index, item in enumerate(items):
        claim = _claim_for_item(item, claims)
        calculation_ids = _string_set(
            item.get("calculation_ids", []), "review_item.calculation_ids"
        )
        item_calculations = [
            calculation
            for calculation in calculations
            if str(_mapping(calculation, "calculation").get("calculation_result_id", ""))
            in calculation_ids
        ]
        rule_ids = _string_set(item.get("rule_ids", []), "review_item.rule_ids")
        item_rules = [
            rule
            for rule in rules
            if str(_mapping(rule, "rule").get("rule_id", "")) in rule_ids
        ]
        item_id = str(item.get("item_id", ""))
        audit_ids = _string_set(item.get("audit_ids", []), "review_item.audit_ids")
        item_audit_records = [
            record
            for record in audit_records
            if (
                str(_mapping(record, "audit record").get("item_id", "")) == item_id
                or str(_mapping(record, "audit record").get("audit_id", "")) in audit_ids
            )
        ]
        exception_codes = _string_set(
            item.get("exception_codes", []), "review_item.exception_codes"
        )
        conflict_codes = _string_set(
            item.get("conflict_codes", []), "review_item.conflict_codes"
        )
        item_exceptions = [
            global_exceptions[code]
            for code in sorted(exception_codes)
            if code in global_exceptions
        ]
        item_conflicts = [
            global_conflicts[code]
            for code in sorted(conflict_codes)
            if code in global_conflicts
        ]

        claim_html = '<p class="empty-state">연결된 주장 기록 없음</p>'
        citation_html = '<p class="empty-state">이 항목에 연결된 인용 근거 없음</p>'
        if claim is not None:
            claim_html = f'<p class="claim-text">{_text(claim.get("text"))}</p>'
            claim_citations = list(citations.get(str(claim.get("claim_id", "")), []))
            has_link_hints = "citation_ids" in item or "evidence_ids" in item
            citation_ids = _string_set(
                item.get("citation_ids", []), "review_item.citation_ids"
            )
            evidence_ids = _string_set(
                item.get("evidence_ids", []), "review_item.evidence_ids"
            )
            linked_citations = (
                [
                    citation
                    for citation in claim_citations
                    if citation.citation_id in citation_ids
                    or citation.evidence_id in evidence_ids
                ]
                if has_link_hints
                else claim_citations
            )
            if linked_citations:
                citation_html = "".join(
                    citation.metadata_html for citation in linked_citations
                )
        evidence_panel_id = f"detail-{index}-evidence"
        rules_panel_id = f"detail-{index}-rules-calculations"
        audit_panel_id = f"detail-{index}-audit-exceptions"
        has_item_audit = bool(item_audit_records or item_exceptions or item_conflicts)
        panels.append(
            "".join(
                (
                    '<article class="detail-panel',
                    " is-selected" if index == 0 else "",
                    f'" data-item-id="{_text(item.get("item_id"))}">',
                    "<h3>항목 ",
                    _text(item_id),
                    '</h3><dl class="item-summary">',
                    f"<div><dt>주장</dt><dd>{_text(item.get('claim_id'))}</dd></div>",
                    f"<div><dt>상태</dt><dd>{_text(item.get('status'))}</dd></div>",
                    f"<div><dt>완결성</dt><dd>{_text(item.get('completeness'))}</dd></div>",
                    "</dl>",
                    f'<section id="{evidence_panel_id}" role="tabpanel" '
                    'aria-labelledby="detail-tab-evidence" data-tab-panel="evidence">',
                    "<h4>주장과 인용 근거</h4>",
                    claim_html,
                    citation_html,
                    "</section>",
                    f'<section id="{rules_panel_id}" role="tabpanel" '
                    'aria-labelledby="detail-tab-rules-calculations" '
                    'data-tab-panel="rules-calculations" hidden>',
                    "<h4>승인 규칙</h4><div class=\"table-scroll\"><table><thead><tr>",
                    "<th>규칙</th><th>버전</th><th>상태</th></tr></thead><tbody>",
                    _table_rows(item_rules, ("rule_id", "rule_version", "status")),
                    "</tbody></table></div>",
                    "<h4>결정론 계산</h4><div class=\"table-scroll\"><table><thead><tr>",
                    "<th>ID</th><th>수식</th><th>버전</th><th>대입</th><th>결과</th>",
                    "<th>비교</th></tr></thead><tbody>",
                    _table_rows(
                        item_calculations,
                        (
                            "calculation_result_id",
                            "formula_id",
                            "formula_version",
                            "substitution",
                            "display_result",
                            "comparison",
                        ),
                    ),
                    "</tbody></table></div></section>",
                    f'<section id="{audit_panel_id}" role="tabpanel" '
                    'aria-labelledby="detail-tab-audit-exceptions" '
                    'data-tab-panel="audit-exceptions" hidden>',
                    "<h4>연결된 감사 사실</h4>",
                    _record_cards(item_audit_records, "이 항목에 연결된 감사 기록 없음"),
                    "<h4>연결된 예외</h4>",
                    _value_list(item_exceptions, "이 항목에 연결된 예외 기록 없음"),
                    "<h4>연결된 충돌</h4>",
                    _value_list(item_conflicts, "이 항목에 연결된 충돌 기록 없음"),
                    (
                        ""
                        if has_item_audit
                        else (
                            '<p class="empty-state unlinked">'
                            "이 항목에 연결된 감사·예외 기록 없음</p>"
                        )
                    ),
                    "</section>",
                    "</article>",
                )
            )
        )
    return "".join(
        (
            '<section id="detail-tabs" aria-labelledby="detail-heading">',
            '<h2 id="detail-heading" class="visually-hidden">선택 항목 상세</h2>',
            '<div role="tablist" aria-label="선택 항목 상세">',
            '<button id="detail-tab-evidence" type="button" role="tab" tabindex="0" '
            'aria-selected="true" aria-controls="detail-0-evidence" '
            'data-detail-tab="evidence">근거</button>',
            '<button id="detail-tab-rules-calculations" type="button" role="tab" '
            'tabindex="-1" aria-selected="false" '
            'aria-controls="detail-0-rules-calculations" '
            'data-detail-tab="rules-calculations">규칙·계산</button>',
            '<button id="detail-tab-audit-exceptions" type="button" role="tab" '
            'tabindex="-1" aria-selected="false" '
            'aria-controls="detail-0-audit-exceptions" '
            'data-detail-tab="audit-exceptions">감사·예외</button>',
            "</div>",
            "".join(panels) or '<p class="empty-state">검토 항목을 선택하세요.</p>',
            "</section>",
        )
    )


def _render_packet_global_review(model: Mapping[str, object]) -> str:
    audit = _mapping(model.get("audit", {}), "audit")
    audit_records = _sequence(audit.get("records", []), "audit.records")
    exceptions = _sequence(model.get("exceptions", []), "exceptions")
    conflicts = _sequence(model.get("conflicts", []), "conflicts")
    abstention_reasons = _sequence(
        model.get("abstention_reasons", []), "abstention_reasons"
    )
    confidence_value = model.get("confidence")
    confidence = (
        {} if confidence_value is None else _mapping(confidence_value, "confidence")
    )
    confidence_factors = _sequence(
        confidence.get("factors", []), "confidence.factors"
    )
    return "".join(
        (
            '<section id="packet-global-review" aria-labelledby="packet-global-heading">',
            '<div class="global-audit-layout">',
            '<div class="section-heading"><h2 id="packet-global-heading">패킷 전체 감사 정보</h2>',
            '<p>특정 항목 소유권을 추론하지 않는 전역 기록</p></div>',
            '<div class="global-review-grid">',
            '<div class="global-card"><h3>Track 감사 상태</h3><dl class="compact-facts">',
            f'<dt>Track A</dt><dd>{_display_value(audit.get("track_a_status"))}</dd>',
            f'<dt>Track B</dt><dd>{_display_value(audit.get("track_b_status"))}</dd>',
            "</dl>",
            _record_cards(audit_records, "패킷 전체 감사 기록 없음"),
            "</div>",
            '<div class="global-card"><h3>전역 예외·충돌</h3><h4>예외</h4>',
            _value_list(exceptions, "전역 예외 없음"),
            "<h4>충돌</h4>",
            _value_list(conflicts, "전역 충돌 없음"),
            "</div>",
            '<div class="global-card" id="abstention-reasons"><h3>전역 기권 사유</h3>',
            _value_list(abstention_reasons, "전역 기권 사유 없음"),
            "</div>",
            '<div class="global-card"><h3>전역 신뢰도 요인</h3>',
            '<dl class="compact-facts">',
            f'<dt>점수</dt><dd>{_display_value(confidence.get("score"))}</dd>',
            f'<dt>수준</dt><dd>{_display_value(confidence.get("level"))}</dd>',
            "</dl>",
            _record_cards(confidence_factors, "전역 신뢰도 요인 없음"),
            "</div></div></div></section>",
        )
    )


def _render_decision_form(model: Mapping[str, object]) -> str:
    decision = _mapping(model.get("decision", {}), "decision")
    options = _sequence(decision.get("allowed_values", []), "decision.allowed_values")
    labels = {
        "SATISFIED": "충족",
        "NOT_SATISFIED": "미충족",
        "CONDITIONAL": "조건부",
        "ADDITIONAL_REVIEW_REQUIRED": "추가 검토",
    }
    option_html = "".join(
        '<label class="decision-option"><input type="radio" name="decision" '
        f'value="{_text(option)}" required><span><strong>'
        f'{_text(labels.get(str(option), str(option)))}</strong><code>{_text(option)}</code>'
        "</span></label>"
        for option in options
    )
    return "".join(
        (
            '<section id="decision-form" aria-labelledby="decision-heading">',
            '<div class="decision-heading"><div><h2 id="decision-heading">검토자의 최종 결정</h2>',
            "<p>기계 패킷과 분리된 검토자 소유의 추가 전용 기록입니다.</p></div>",
            '<span class="authority-badge">인간 검토 필요</span></div>',
            '<form action="./decision" method="post">',
            '<fieldset class="decision-choices"><legend>결정 선택</legend>',
            option_html
            or (
                '<label class="decision-option"><input type="radio" name="decision" '
                'value="" required disabled><span><strong>허용된 결정 값 없음</strong>'
                "</span></label>"
            ),
            "</fieldset>",
            '<div class="decision-fields">',
            '<label>검토자 ID<input name="reviewer_id" autocomplete="name" required></label>',
            '<label>검토 시각<input name="reviewed_at" '
            'placeholder="ISO-8601 시간대 포함" required></label>',
            '<label class="packet-hash">패킷 SHA-256<input name="packet_sha256" '
            f'value="{_text(decision.get("packet_sha256"))}" readonly required></label>',
            "</div>",
            '<label class="decision-notes">판정 근거 메모<textarea name="notes" rows="3" required '
            'placeholder="검토자가 확정한 근거와 후속 조치를 기록합니다."></textarea></label>',
            '<div class="decision-actions"><button class="primary-action" '
            'type="submit">결정 확정</button>',
            '<button type="button" data-download-decision>결정 JSON 다운로드</button></div>',
            '<p class="form-status" aria-live="polite"></p>',
            "</form></section>",
        )
    )


def _model_json(model: Mapping[str, object]) -> str:
    """Serialize the normalized projection safely for the inline controller."""
    encoded = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_review_html(view_model: Mapping[str, object], page_image_root: Path) -> str:
    """Render an archival Review Workspace without editable machine fields."""
    model = _mapping(view_model, "view_model")
    css = (Path(__file__).with_name("assets") / "review.css").read_text(encoding="utf-8")
    script = (Path(__file__).with_name("assets") / "review.js").read_text(encoding="utf-8")
    claims = _sequence(model.get("claims", []), "claims")
    assets = _page_assets(claims, page_image_root)
    citations: dict[str, list[_CitationRender]] = {}
    overlays: dict[str, list[str]] = {}
    claim_mappings: list[Mapping[str, object]] = []
    for claim_value in claims:
        claim = _mapping(claim_value, "claim")
        claim_mappings.append(claim)
        claim_id = str(claim.get("claim_id", ""))
        citations[claim_id] = []
        for citation_value in _sequence(claim.get("citations", []), "citations"):
            citation = _mapping(citation_value, "citation")
            asset_key, asset = assets[_citation_identity(citation)]
            rendered = _citation_render(
                citation,
                asset_key=asset_key,
                page_asset=asset,
            )
            citations[claim_id].append(rendered)
            overlays.setdefault(asset_key, []).append(rendered.overlay_html)
    items = _review_items(model, claims)
    calculations = _sequence(model.get("calculations", []), "calculations")
    rules = _sequence(model.get("rules", []), "rules")
    audit = _mapping(model.get("audit", {}), "audit")
    exceptions = _sequence(model.get("exceptions", []), "exceptions")
    conflicts = _sequence(model.get("conflicts", []), "conflicts")
    return "".join(
        (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_text(model.get('run_id'))} 근거 검토</title><style>{css}</style>",
            '</head><body><div class="app-shell" data-viewer-mode="compare">',
            _render_status_band(model),
            '<main class="review-workspace">',
            _render_summary(model),
            _render_review_items(items),
            _render_evidence_viewer(assets, overlays),
            _render_detail_tabs(
                items=items,
                claims=claim_mappings,
                citations=citations,
                calculations=calculations,
                rules=rules,
                audit=audit,
                exceptions=exceptions,
                conflicts=conflicts,
            ),
            _render_packet_global_review(model),
            _render_decision_form(model),
            "</main>",
            '<footer class="process-strip" aria-label="검토 절차">',
            '<strong>증거 준비</strong><span>→</span><strong>결정론 엔진</strong><span>→</span>',
            '<strong>Track A 설명</strong><span>→</span>'
            '<strong>Track B 감사</strong><span>→</span>',
            '<strong>인간 최종 판정</strong></footer></div>',
            f'<script id="review-model" type="application/json">{_model_json(model)}</script>',
            f"<script>{script}</script>",
            "</body></html>",
        )
    )


def write_review_html(
    view_model: Mapping[str, object],
    page_image_root: Path,
    output: Path,
) -> Path:
    """Exclusively write reviewer HTML."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(render_review_html(view_model, page_image_root))
    return output
