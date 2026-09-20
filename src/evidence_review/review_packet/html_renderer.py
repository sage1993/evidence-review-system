"""Self-contained, print-safe Review Workspace rendering."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import cast

from evidence_review.review_packet.icons import icon_svg
from evidence_review.review_packet.page_image_verifier import (
    VerifiedPageImage,
    verify_review_page_images,
)
from evidence_review.review_packet.presentation import (
    evidence_type_label,
    localized_status,
    review_presentation_css,
)
from evidence_review.review_packet.quote_presentation import render_quote
from evidence_review.review_packet.render_audit import (
    render_audit_details,
    render_citation_audit,
    render_item_audit,
)
from evidence_review.review_packet.render_case_visual_lazy import (
    case_visual_css,
    render_case_visual_review,
)
from evidence_review.review_packet.render_decision import render_decision_form
from evidence_review.review_packet.render_issue_results import render_issue_results
from evidence_review.review_packet.render_summary import (
    render_additional_review,
    render_status_band,
    render_summary,
    visual_shell_css,
)
from evidence_review.review_packet.render_workspace import render_workspace


@dataclass(frozen=True, slots=True)
class _PageAsset:
    data_uri: str
    pdf_width: float
    pdf_height: float
    rotation: int = 0
    origin_x: float = 0.0
    origin_y: float = 0.0
    box_kind: str = "MEDIA_BOX"
    protected_src: str | None = None


@dataclass(frozen=True, slots=True)
class _CitationRender:
    citation_id: str
    evidence_id: str
    asset_key: str
    metadata_html: str
    overlay_html: str
    citation: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _ViewerDocument:
    document_id: str
    document_name: str
    revision_id: str
    pages: tuple[tuple[str, int, _PageAsset], ...]


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



def _citation_identity(citation: Mapping[str, object]) -> tuple[str, int, str]:
    return (
        str(citation.get("revision_id", "")),
        _page_number(citation.get("page_number")),
        str(citation.get("source_hash", "")),
    )


def _page_assets(
    verified_pages: Sequence[VerifiedPageImage],
    *,
    protected: bool = False,
) -> dict[tuple[str, int, str], tuple[str, _PageAsset]]:
    """Project already-verified pages into renderer-only data URIs."""
    assets: dict[tuple[str, int, str], tuple[str, _PageAsset]] = {}
    for index, verified in enumerate(verified_pages, start=1):
        identity = (
            verified.revision_id,
            verified.page_number,
            verified.source_hash,
        )
        if identity in assets:
            raise ValueError("duplicate verified page image identity")
        assets[identity] = (
            f"page-{index}",
            _PageAsset(
                data_uri=(
                    ""
                    if protected
                    else "data:image/png;base64,"
                    + base64.b64encode(verified.image_bytes).decode("ascii")
                ),
                pdf_width=verified.pdf_width,
                pdf_height=verified.pdf_height,
                rotation=verified.rotation,
                origin_x=verified.origin_x,
                origin_y=verified.origin_y,
                box_kind=verified.box_kind,
                protected_src=(
                    f"./page-images/{verified.revision_id}/{verified.page_number}/{verified.source_hash}"
                    if protected
                    else None
                ),
            ),
        )
    return assets


def _viewer_documents(
    claims: Sequence[object],
    assets: Mapping[tuple[str, int, str], tuple[str, _PageAsset]],
) -> tuple[_ViewerDocument, ...]:
    order: list[tuple[str, str]] = []
    explicit_names: dict[tuple[str, str], str] = {}
    display_names: dict[tuple[str, str], str] = {}
    pages: dict[tuple[str, str], list[tuple[str, int, _PageAsset]]] = {}
    seen_pages: dict[tuple[str, str], set[str]] = {}
    asset_owner: dict[str, tuple[str, str]] = {}

    for claim_value in claims:
        claim = _mapping(claim_value, "claim")
        for citation_value in _sequence(claim.get("citations", []), "citations"):
            citation = _mapping(citation_value, "citation")
            revision_id = str(citation.get("revision_id", ""))
            document_id = str(citation.get("document_id", "")) or revision_id
            if not revision_id or not document_id:
                raise ValueError("citation document/revision identity is required")
            key = (document_id, revision_id)
            explicit_name = str(citation.get("document_name", "")).strip()
            fallback_name = document_id or revision_id
            if key not in pages:
                order.append(key)
                pages[key] = []
                seen_pages[key] = set()
                display_names[key] = explicit_name or fallback_name
                if explicit_name:
                    explicit_names[key] = explicit_name
            elif explicit_name:
                previous = explicit_names.get(key)
                if previous is not None and previous != explicit_name:
                    raise ValueError("conflicting document names for one document revision")
                explicit_names[key] = explicit_name
                display_names[key] = explicit_name

            identity = _citation_identity(citation)
            asset_key, asset = assets[identity]
            previous_owner = asset_owner.get(asset_key)
            if previous_owner is not None and previous_owner != key:
                raise ValueError("page asset is referenced by multiple document identities")
            asset_owner[asset_key] = key
            if asset_key not in seen_pages[key]:
                pages[key].append((asset_key, identity[1], asset))
                seen_pages[key].add(asset_key)

    return tuple(
        _ViewerDocument(
            document_id=document_id,
            document_name=display_names[(document_id, revision_id)],
            revision_id=revision_id,
            pages=tuple(pages[(document_id, revision_id)]),
        )
        for document_id, revision_id in order
    )


def _citation_render(
    value: object,
    *,
    asset_key: str,
    page_asset: _PageAsset,
    source_id: str,
) -> _CitationRender:
    citation = _mapping(value, "citation")
    _revision_id, page_number, _source_hash = _citation_identity(citation)
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
    bbox_text = ", ".join(str(item) for item in (left, bottom, right, top))
    citation_id = str(citation.get("citation_id", ""))
    evidence_id = str(citation.get("evidence_id", ""))
    metadata_html = "".join(
        (
            '<article class="citation" ',
            f'data-asset-key="{_text(asset_key)}" ',
            f'data-source-id="{_text(source_id)}" ',
            f'data-citation-id="{_text(citation_id)}" ',
            f'data-evidence-id="{_text(evidence_id)}" tabindex="0" ',
            'role="button" aria-label="근거 선택">',
            f'<p class="citation-document">{_text(citation.get("document_name"))}</p>',
            f"<h4>{_text(citation.get('title'))}</h4>",
            '<p class="citation-location">페이지 ',
            str(page_number),
            "</p>",
            f"<blockquote>{_text(citation.get('quote'))}</blockquote>",
            '<p class="bbox-location visually-hidden"><strong>인용 좌표</strong> ',
            f'<code data-bbox="{_text(bbox_text.replace(" ", ""))}">',
            _text(bbox_text),
            "</code></p>",
            '<button class="evidence-link" type="button" ',
            f'data-asset-key="{_text(asset_key)}" ',
            f'data-source-id="{_text(source_id)}" ',
            f'data-evidence-id="{_text(evidence_id)}">',
            icon_svg("search", size=14),
            " 원문 위치 보기</button>",
            render_citation_audit(citation),
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
            'preserveAspectRatio="none" aria-label="인용 위치">',
            f'<rect x="{rect_x}" y="{rect_y}" width="{rect_width}" ',
            f'height="{rect_height}"></rect>',
            "</svg>",
        )
    )
    return _CitationRender(
        citation_id=citation_id,
        evidence_id=evidence_id,
        asset_key=asset_key,
        metadata_html=metadata_html,
        overlay_html=overlay_html,
        citation=citation,
    )


def _string_set(value: object, field: str) -> set[str]:
    values: set[str] = set()
    for index, item in enumerate(_sequence(value, field)):
        if not isinstance(item, str):
            raise ValueError(f"{field}[{index}] must be a string")
        values.add(item)
    return values


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
            "status": "INDETERMINATE",
            "completeness": "UNKNOWN",
        }
        for claim in (_mapping(value, "claim") for value in claims)
    ]


def _render_evidence_list(
    items: Sequence[Mapping[str, object]],
    claims: Sequence[Mapping[str, object]],
    citations: Mapping[str, Sequence[_CitationRender]],
) -> str:
    cards: list[str] = []
    card_index = 0
    for item in items:
        claim = _claim_for_item(item, claims)
        linked = list(citations.get(str(claim.get("claim_id", "")), [])) if claim else []
        entries: Sequence[_CitationRender | None] = linked or [None]
        for linked_citation in entries:
            citation = linked_citation.citation if linked_citation is not None else {}
            page_number = citation.get("page_number", "-")
            evidence_type = evidence_type_label(citation.get("evidence_type"))
            asset_key = linked_citation.asset_key if linked_citation is not None else ""
            evidence_id = linked_citation.evidence_id if linked_citation is not None else ""
            card_index += 1
            type_html = (
                f'<span class="evidence-type-pill">{icon_svg("check", size=12)}'
                f"{_text(evidence_type)}</span>"
                if evidence_type
                else ""
            )
            cards.append(
                "".join(
                    (
                        '<button class="review-item evidence-card',
                        " is-selected" if card_index == 1 else "",
                        '" type="button" ',
                        f'data-item-id="{_text(item.get("item_id"))}" ',
                        f'data-asset-key="{_text(asset_key)}" ',
                        f'data-evidence-id="{_text(evidence_id)}" ',
                        f'aria-pressed="{"true" if card_index == 1 else "false"}">',
                        f'<span class="evidence-index">{card_index}</span>',
                        '<span class="evidence-card-body">',
                        '<span class="evidence-title">',
                        _text(citation.get("document_name", "판단 근거")),
                        "</span>",
                        '<span class="evidence-meta">',
                        _text(evidence_type or "원문 근거"),
                        " · p.",
                        _text(page_number),
                        "</span>",
                        f'<span class="evidence-quote">{_text(citation.get("quote"))}</span>',
                        type_html,
                        "</span>",
                        f'<span class="evidence-doc-icon">{icon_svg("file-text", size=16)}</span>',
                        "</button>",
                        '<details class="evidence-full-text">'
                        '<summary>근거 내용 전체 보기</summary>',
                        f'<p class="evidence-meta">{_text(citation.get("title"))}</p>',
                        render_quote(str(citation.get("quote") or "")),
                        "</details>",
                    )
                )
            )
    return "".join(
        (
            '<nav id="review-items" aria-labelledby="evidence-list-heading">',
            '<div class="panel-heading"><h2 id="evidence-list-heading">판단 근거</h2>',
            '<span class="evidence-sort-label">문서별 · 관련도순</span></div>',
            '<div class="review-item-list">',
            "".join(cards) or '<p class="empty-state">결과에 연결된 판단 근거가 없습니다.</p>',
            "</div>",
            '<p class="evidence-selection-hint">',
            icon_svg("info", size=15),
            " 선택한 근거를 클릭하면 PDF에서 해당 부분이 강조됩니다.</p>",
            "</nav>",
        )
    )


def _render_evidence_viewer(
    documents: Sequence[_ViewerDocument],
    overlays: Mapping[str, Sequence[str]],
) -> str:
    pages: list[str] = []
    thumbnails: list[str] = []
    source_options: list[str] = []
    source_by_asset: dict[str, str] = {}

    for document_index, document in enumerate(documents):
        source_id = f"source-{document_index + 1}"
        source_options.append(
            f'<option value="{source_id}"{" selected" if document_index == 0 else ""}>'
            f'{_text(document.document_name)}</option>'
        )
        source_count = len(document.pages)
        for page_index, (asset_key, page_number, asset) in enumerate(document.pages):
            source_by_asset[asset_key] = source_id
            active = document_index == 0 and page_index == 0
            hidden = "" if document_index == 0 else " hidden"
            common = (
                f'data-source-id="{source_id}" '
                f'data-original-page="{page_number}" '
                f'data-source-position="{page_index + 1}" '
                f'data-source-count="{source_count}"'
            )
            thumbnails.append(
                "".join(
                    (
                        f'<button class="page-thumb{" is-active" if active else ""}" ',
                        'type="button" ',
                        f'data-page-select="{_text(asset_key)}" {common}{hidden} ',
                        f'aria-label="{_text(document.document_name)} 원문 페이지 {page_number}">',
                        f'<img class="page-thumb-image" data-page-image-for="{_text(asset_key)}" ',
                        'alt="" aria-hidden="true">',
                        f"<span>{page_number}</span></button>",
                    )
                )
            )
            pages.append(
                "".join(
                    (
                        '<figure class="evidence-page',
                        " is-active" if active else "",
                        f'" id="evidence-{asset_key}" data-asset-key="{asset_key}" ',
                        f'{common}{hidden} tabindex="-1">',
                        '<div class="page-stage"><div class="page-canvas">',
                        f'<img data-page-image-source="{_text(asset_key)}" ',
                        f'alt="{_text(document.document_name)} 검증된 원본 페이지 {page_number}" ',
                        (
                            f'data-page-src="{_text(asset.protected_src)}" src="">'
                            if asset.protected_src is not None
                            else f'src="{asset.data_uri}">'
                        ),
                        '<div class="overlay-layer">',
                        "".join(overlays.get(asset_key, [])),
                        "</div></div></div>",
                        f"<figcaption>{_text(document.document_name)} · 원문 ",
                        f"p.{page_number}</figcaption>",
                        "</figure>",
                    )
                )
            )

    first_document = documents[0] if documents else None
    first_page = first_document.pages[0] if first_document and first_document.pages else None
    current_original = first_page[1] if first_page else 1
    current_count = len(first_document.pages) if first_document else 0
    if len(documents) > 1:
        source_control = "".join(
            (
                '<label class="pdf-source-control">원본 문서 ',
                '<select data-source-select class="pdf-source-select" aria-label="원본 문서 선택">',
                "".join(source_options),
                "</select></label>",
            )
        )
    elif first_document is not None:
        source_control = (
            '<span class="pdf-source-label" data-source-label>'
            f'{_text(first_document.document_name)}</span>'
        )
    else:
        source_control = '<span class="pdf-source-label" data-source-label>원본 문서 없음</span>'

    return "".join(
        (
            '<section id="evidence-viewer" aria-labelledby="pdf-heading">',
            '<span class="section-kicker visually-hidden">2. 판단 근거</span>',
            '<div class="viewer-toolbar">',
            source_control,
            '<div class="viewer-mode-controls" role="group" aria-label="근거 표시 방식">',
            '<button type="button" data-viewer-mode="original" aria-pressed="false">원문</button>',
            '<button type="button" data-viewer-mode="evidence" aria-pressed="false">',
            '근거 강조</button>',
            '<button type="button" data-viewer-mode="compare" aria-pressed="true">',
            '원문 + 강조</button>',
            '</div>',
            '<div class="pdf-page-controls"><button type="button" data-page-prev aria-label="',
            '이전 근거 페이지">',
            icon_svg("chevron-left", size=15),
            "</button>",
            '<span>근거 페이지 <strong data-current-source-position>1</strong> / ',
            f'<span data-current-source-count>{current_count}</span> · 원문 p.',
            f'<strong data-current-original-page>{current_original}</strong></span>',
            '<button type="button" data-page-next aria-label="다음 근거 페이지">',
            icon_svg("chevron-right", size=15),
            "</button></div>",
            '<div class="pdf-zoom-controls"><button type="button" data-zoom-out aria-label="축소">',
            icon_svg("minus", size=15),
            "</button><span data-zoom-value>100%</span>",
            '<button type="button" data-zoom-in aria-label="확대">',
            icon_svg("plus", size=15),
            '</button><button type="button" data-fullscreen aria-label="전체 화면">',
            icon_svg("maximize", size=15),
            "</button></div>",
            "</div>",
            '<div class="viewer-body"><aside class="thumbnail-rail" aria-label="인용된 ',
            '원본 페이지 미리보기">',
            "".join(thumbnails) or '<p class="empty-state">페이지 없음</p>',
            '</aside><div class="page-viewport">',
            "".join(pages) or '<p class="empty-state">검증된 원본 페이지가 없습니다.</p>',
            "</div></div>",
            '<p class="viewer-footnote">검토에 사용된 원본 문서의 검증된 페이지 ',
            '이미지를 표시합니다.</p>',
            "</section>",
        )
    )


def _claim_for_item(
    item: Mapping[str, object], claims: Sequence[Mapping[str, object]]
) -> Mapping[str, object] | None:
    claim_id = item.get("claim_id")
    return next((claim for claim in claims if claim.get("claim_id") == claim_id), None)


def _related_records(
    item: Mapping[str, object],
    records: Sequence[object],
    *,
    id_field: str,
    item_field: str,
    single_item: bool,
) -> list[Mapping[str, object]]:
    ids = _string_set(item.get(item_field, []), f"review_item.{item_field}")
    if not ids and single_item:
        return [_mapping(record, id_field) for record in records]
    return [
        record
        for value in records
        for record in [_mapping(value, id_field)]
        if str(record.get(id_field, "")) in ids
    ]


def _render_rule_calculation_panel(
    rules: Sequence[Mapping[str, object]],
    calculations: Sequence[Mapping[str, object]],
) -> str:
    blocks: list[str] = []
    if rules:
        rows = "".join(
            "<li><strong>규칙 판정</strong><span>"
            + _text(localized_status(rule.get("status")))
            + "</span></li>"
            for rule in rules
        )
        blocks.append(f'<div class="deterministic-block"><h4>규칙 검토</h4><ul>{rows}</ul></div>')
    if calculations:
        calculation_rows: list[str] = []
        for calculation in calculations:
            raw_inputs = calculation.get("inputs")
            inputs = (
                cast(Mapping[str, object], raw_inputs)
                if isinstance(raw_inputs, Mapping)
                else {}
            )
            raw_units = calculation.get("input_units")
            input_units = (
                cast(Mapping[str, object], raw_units)
                if isinstance(raw_units, Mapping)
                else {}
            )
            input_summary = " · ".join(
                f"{key}={value}" + (f" {input_units[key]}" if input_units.get(key) else "")
                for key, value in sorted(inputs.items())
            )
            calculation_rows.append(
                "".join(
                    (
                        "<li><strong>계산 결과</strong><span>",
                        _text(calculation.get("display_result")),
                        "</span><small>",
                        _text(calculation.get("substitution")),
                        "</small><small class=\"calculation-authority\">",
                        _text(input_summary),
                        "</small><small class=\"calculation-policy\">원시 결과 ",
                        _text(calculation.get("raw_result")),
                        " · precision ",
                        _text(calculation.get("precision")),
                        " · ",
                        _text(calculation.get("rounding")),
                        " · ",
                        _text(calculation.get("intermediate_rounding_policy")),
                        "</small></li>",
                    )
                )
            )
        rows = "".join(calculation_rows)
        blocks.append(f'<div class="deterministic-block"><h4>계산</h4><ul>{rows}</ul></div>')
    return "".join(blocks)


def _render_detail_tabs(
    *,
    items: Sequence[Mapping[str, object]],
    claims: Sequence[Mapping[str, object]],
    citations: Mapping[str, Sequence[_CitationRender]],
    calculations: Sequence[object],
    rules: Sequence[object],
) -> str:
    panels: list[str] = []
    show_deterministic = bool(calculations or rules)
    for index, item in enumerate(items):
        claim = _claim_for_item(item, claims)
        single_item = len(items) == 1
        item_calculations = _related_records(
            item,
            calculations,
            id_field="calculation_result_id",
            item_field="calculation_ids",
            single_item=single_item,
        )
        item_rules = _related_records(
            item,
            rules,
            id_field="rule_id",
            item_field="rule_ids",
            single_item=single_item,
        )
        claim_html = '<p class="empty-state">연결된 설명이 없습니다.</p>'
        citation_html = '<p class="empty-state">연결된 인용 근거가 없습니다.</p>'
        if claim is not None:
            claim_html = f'<p class="claim-text">{_text(claim.get("text"))}</p>'
            linked = list(citations.get(str(claim.get("claim_id", "")), []))
            if linked:
                citation_html = "".join(item.metadata_html for item in linked)
        evidence_panel_id = f"detail-{index}-evidence"
        deterministic_panel_id = f"detail-{index}-rules-calculations"
        panels.append(
            "".join(
                (
                    '<article class="detail-panel',
                    " is-selected" if index == 0 else "",
                    f'" data-item-id="{_text(item.get("item_id"))}">',
                    '<h3 class="detail-title">검토 근거 ',
                    str(index + 1) if len(items) > 1 else "",
                    "</h3>",
                    f'<section id="{evidence_panel_id}" role="tabpanel" '
                    'aria-labelledby="detail-tab-evidence" data-tab-panel="evidence">',
                    claim_html,
                    citation_html,
                    "</section>",
                    (
                        "".join(
                            (
                                f'<section id="{deterministic_panel_id}" role="tabpanel" ',
                                'aria-labelledby="detail-tab-rules-calculations" ',
                                'data-tab-panel="rules-calculations" hidden>',
                                _render_rule_calculation_panel(item_rules, item_calculations),
                                "</section>",
                            )
                        )
                        if show_deterministic
                        else ""
                    ),
                    render_item_audit(
                        item,
                        rules=item_rules,
                        calculations=item_calculations,
                    ),
                    "</article>",
                )
            )
        )
    tablist = ""
    if show_deterministic:
        tablist = "".join(
            (
                '<div role="tablist" aria-label="선택 항목 상세">',
                '<button id="detail-tab-evidence" type="button" role="tab" tabindex="0" ',
                'aria-selected="true" aria-controls="detail-0-evidence" ',
                'data-detail-tab="evidence">근거</button>',
                '<button id="detail-tab-rules-calculations" type="button" role="tab" ',
                'tabindex="-1" aria-selected="false" ',
                'aria-controls="detail-0-rules-calculations" ',
                'data-detail-tab="rules-calculations">규칙·계산</button>',
                "</div>",
            )
        )
    return "".join(
        (
            '<section id="detail-tabs" aria-labelledby="detail-heading">',
            '<h2 id="detail-heading" class="visually-hidden">판단 근거 상세</h2>',
            tablist,
            "".join(panels) or '<p class="empty-state">연결된 검토 근거가 없습니다.</p>',
            "</section>",
        )
    )


def _model_json(model: Mapping[str, object]) -> str:
    encoded = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _package_version() -> str:
    try:
        return package_version("evidence-review-system")
    except PackageNotFoundError:
        return "development"


def _render_process_footer(model: Mapping[str, object]) -> str:
    metadata = _mapping(model.get("metadata") or {}, "metadata")
    created_at = str(
        metadata.get("created_at") or metadata.get("generated_at") or model.get("created_at") or ""
    )
    return "".join(
        (
            '<footer class="process-strip" aria-label="리뷰 시스템 정보">',
            '<div class="product-identity"><strong>Evidence Review System</strong>',
            f"<span>v{_text(_package_version())}</span></div>",
            '<div class="footer-meta">',
            '<span>생성일 <time data-created-at="',
            _text(created_at),
            '">',
            _text(created_at),
            "</time></span>",
            '<span>\uAE30\uACC4 \uD3C9\uAC00\uB294 \uCD5C\uC885 ',
            '\uD310\uC815\uC774 \uC544\uB2D9\uB2C8\uB2E4.</span>',
            "</div></footer>",
        )
    )


def _render_presentation_guidance(
    model: Mapping[str, object],
    *,
    protected: bool,
) -> str:
    run_id = _text(model.get("run_id"))
    serve_command = (
        "evidence-review review-run serve --workspace &lt;workspace&gt; --run-id "
        f"{run_id}"
    )
    if protected:
        return "".join(
            (
                '<aside class="presentation-guidance protected-file-guidance" '
                'data-protected-file-guidance hidden>',
                "<h2>보호된 검토기는 파일로 열 수 없습니다</h2>",
                "<p>보호된 도면은 파일 경로가 아니라 로컬 보호 서버에서만 표시됩니다. ",
                "아래 명령으로 검토기를 실행하십시오.</p>",
                '<details class="presentation-advanced">',
                "<summary>고급 실행 정보</summary>",
                f"<code>{serve_command}</code>",
                "</details>",
                "</aside>",
            )
        )
    return "".join(
        (
            '<aside class="presentation-guidance archival-guidance" '
            'data-archival-static-mode="true">',
            "<h2>보관용 정적 HTML</h2>",
            "<p>이 파일은 보관·인쇄용 정적 검토 화면입니다. 결정은 이 HTML에 저장되지 않으며, ",
            "보호된 검토기에서 기록해야 합니다.</p>",
            '<details class="presentation-advanced">',
            "<summary>고급 실행 정보</summary>",
            f"<p>보호된 검토기 실행: <code>{serve_command}</code></p>",
            "</details>",
            "</aside>",
        )
    )


def _render_review_html(
    view_model: Mapping[str, object],
    page_image_root: Path,
    *,
    protected: bool,
) -> str:
    """Render archive or protected Review Workspace from an explicit model."""
    model = _mapping(view_model, "view_model")
    assets_path = Path(__file__).with_name("assets")
    tokens_css = (assets_path / "tokens.css").read_text(encoding="utf-8")
    css_modules = tuple(
        (
            name,
            (assets_path / name).read_text(encoding="utf-8"),
        )
        for name in (
            "shell.css",
            "viewer.css",
            "issues.css",
            "decision.css",
            "audit.css",
            "responsive.css",
        )
    )
    css_bundle = (
        "\n".join(
            f"/* {name} */\n{module_css}" for name, module_css in css_modules
        )
        + "\n/* shared presentation tokens */\n"
        + review_presentation_css()
        + "\n/* case visual workspace */\n"
        + case_visual_css()
        + "\n/* case visual shell */\n"
        + visual_shell_css()
        + "\n/* Review Workspace v2 tokens */\n"
        + tokens_css
        + (assets_path / "review_ux.css").read_text(encoding="utf-8")
    )
    script = (assets_path / "review.js").read_text(encoding="utf-8")
    claims = _sequence(model.get("claims", []), "claims")
    verified_pages = verify_review_page_images(model, page_image_root)
    assets = _page_assets(verified_pages, protected=protected)
    documents = _viewer_documents(claims, assets)
    source_by_asset = {
        asset_key: f"source-{document_index + 1}"
        for document_index, document in enumerate(documents)
        for asset_key, _page_number_value, _asset in document.pages
    }
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
                source_id=source_by_asset[asset_key],
            )
            citations[claim_id].append(rendered)
            overlays.setdefault(asset_key, []).append(rendered.overlay_html)
    items = _review_items(model, claims)
    calculations = _sequence(model.get("calculations", []), "calculations")
    rules = _sequence(model.get("rules", []), "rules")
    visual_review = render_case_visual_review(model)
    evidence_workspace = (
        visual_review
        if visual_review
        else "".join(
            (
                _render_evidence_list(items, claim_mappings, citations),
                _render_evidence_viewer(documents, overlays),
            )
        )
    )
    detail_issue_results = "".join(
        (
            "" if visual_review else render_additional_review(model),
            render_issue_results(model),
            _render_detail_tabs(
                items=items,
                claims=claim_mappings,
                citations=citations,
                calculations=calculations,
                rules=rules,
            ),
        )
    )
    return "".join(
        (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<link rel="icon" href="data:,">',
            f"<title>근거 검토 · {_text(model.get('question'))}</title><style>{css_bundle}</style>",
            '</head><body><div class="app-shell" data-surface="formal-review" '
            'data-viewer-mode="compare"',
            ' data-protected-presentation="true"' if protected else "",
            ' data-archival-static-mode="true"' if not protected else "",
            '>',
            render_workspace(
                model,
                status_question="".join(
                    (
                        render_status_band(model),
                        _render_presentation_guidance(model, protected=protected),
                        render_summary(model),
                    )
                ),
                evidence_workspace=evidence_workspace,
                detail_issue_results=detail_issue_results,
                human_decision=render_decision_form(model, initially_hidden=False),
                audit=render_audit_details(model),
            ),
            _render_process_footer(model),
            "</div>",
            f'<script id="review-model" type="application/json">{_model_json(model)}</script>',
            f"<script>{script}</script>",
            "</body></html>",
        )
    )


def render_review_html(view_model: Mapping[str, object], page_image_root: Path) -> str:
    """Render the immutable archival Review Workspace."""
    return _render_review_html(view_model, page_image_root, protected=False)


def render_protected_review_html(
    view_model: Mapping[str, object],
    page_image_root: Path,
) -> str:
    """Render the protected Review Workspace without embedded raster payloads."""
    html = _render_review_html(view_model, page_image_root, protected=True)
    if "data:image/" in html:
        raise ValueError("protected presentation contains embedded raster payload")
    return html


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


def render_protected_review_entry(
    view_model: Mapping[str, object],
    page_image_root: Path,
) -> str:
    """Render a payload-free entry; inspection requires the protected server."""
    from evidence_review.review_packet.protected_projection import (
        build_protected_review_projection,
    )

    projection = build_protected_review_projection(view_model, page_image_root)
    return (
        '<!doctype html><html lang="ko"><meta charset="utf-8">'
        '<title>Formal Review</title><body>'
        '<main><h1>Formal Review</h1>'
        '<p>기계 평가는 최종 판정이 아닙니다.</p>'
        '<p>보호된 검토 서버에서 이 RUN을 여세요.</p>'
        '<p>PROTECTED_REVIEW_REQUIRED</p></main>'
        '<script id="review-model" type="application/json">'
        + _model_json(projection.model)
        + '</script></body></html>'
    )


def write_protected_review_entry(
    view_model: Mapping[str, object],
    page_image_root: Path,
    output: Path,
) -> Path:
    """Exclusively persist the protected entry for one finalized RUN."""
    html = render_protected_review_entry(view_model, page_image_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(html)
    return output
