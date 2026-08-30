"""Self-contained, print-safe Review Workspace rendering."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import cast

from evidence_review.contracts.legacy_formats import LEGACY_PAGE_IMAGE_FORMAT
from evidence_review.review_packet.icons import icon_svg
from evidence_review.review_packet.presentation import evidence_type_label, localized_status
from evidence_review.review_packet.render_audit import (
    render_audit_details,
    render_citation_audit,
    render_item_audit,
)
from evidence_review.review_packet.render_decision import render_decision_form
from evidence_review.review_packet.render_summary import (
    render_additional_review,
    render_status_band,
    render_summary,
)
from evidence_review.review_packet.render_workspace import render_workspace

_GEOMETRY_TOLERANCE = 0.5
_PAGE_IMAGE_FORMAT = "evidence-review/page-image"


@dataclass(frozen=True, slots=True)
class _PageAsset:
    data_uri: str
    pdf_width: float
    pdf_height: float
    rotation: int = 0
    origin_x: float = 0.0
    origin_y: float = 0.0
    box_kind: str = "MEDIA_BOX"


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
    if (
        metadata.get("format") not in {_PAGE_IMAGE_FORMAT, LEGACY_PAGE_IMAGE_FORMAT}
        or metadata.get("version") != 1
    ):
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
    origin_x_value = metadata.get("origin_x", 0.0)
    origin_y_value = metadata.get("origin_y", 0.0)
    if (
        isinstance(origin_x_value, bool)
        or isinstance(origin_y_value, bool)
        or not isinstance(origin_x_value, (int, float))
        or not isinstance(origin_y_value, (int, float))
    ):
        raise ValueError("page image origin is invalid")
    origin_x, origin_y = float(origin_x_value), float(origin_y_value)
    if not all(
        value == value and value not in (float("inf"), float("-inf"))
        for value in (origin_x, origin_y)
    ):
        raise ValueError("page image origin is invalid")
    box_kind = metadata.get("box_kind", "MEDIA_BOX")
    if box_kind not in {"CROP_BOX", "MEDIA_BOX"}:
        raise ValueError("page image box kind is invalid")
    return _PageAsset(
        data_uri="data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii"),
        pdf_width=pdf_width,
        pdf_height=pdf_height,
        rotation=rotation,
        origin_x=origin_x,
        origin_y=origin_y,
        box_kind=box_kind,
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
    expected = (
        ("page_origin_x", page_asset.origin_x),
        ("page_origin_y", page_asset.origin_y),
        ("page_rotation", page_asset.rotation),
        ("page_box_kind", page_asset.box_kind),
    )
    for field, value in expected:
        provided = citation.get(field)
        if provided is not None and provided != value:
            raise ValueError(f"PAGE_RENDER_GEOMETRY_MISMATCH: {field}")


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
                        _text(citation.get("title")),
                        " · p.",
                        _text(page_number),
                        "</span>",
                        f'<span class="evidence-quote">{_text(citation.get("quote"))}</span>',
                        type_html,
                        "</span>",
                        f'<span class="evidence-doc-icon">{icon_svg("file-text", size=16)}</span>',
                        "</button>",
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
                        f'src="{asset.data_uri}">',
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
        rows = "".join(
            "".join(
                (
                    "<li><strong>계산 결과</strong><span>",
                    _text(calculation.get("display_result")),
                    "</span><small>",
                    _text(calculation.get("substitution")),
                    "</small></li>",
                )
            )
            for calculation in calculations
        )
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


def render_review_html(view_model: Mapping[str, object], page_image_root: Path) -> str:
    """Render the default non-developer Review Workspace."""
    model = _mapping(view_model, "view_model")
    assets_path = Path(__file__).with_name("assets")
    css = (assets_path / "review.css").read_text(encoding="utf-8")
    responsive_css = (assets_path / "review_responsive.css").read_text(encoding="utf-8")
    css_bundle = css + "\n/* review_responsive.css */\n" + responsive_css
    script = (assets_path / "review.js").read_text(encoding="utf-8")
    claims = _sequence(model.get("claims", []), "claims")
    assets = _page_assets(claims, page_image_root)
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
    return "".join(
        (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>근거 검토 · {_text(model.get('question'))}</title><style>{css_bundle}</style>",
            '</head><body><div class="app-shell" data-viewer-mode="compare">',
            render_status_band(model),
            render_workspace(
                model,
                "".join(
                    (
                        render_summary(model),
                        render_additional_review(model),
                        _render_evidence_list(items, claim_mappings, citations),
                        _render_evidence_viewer(documents, overlays),
                        _render_detail_tabs(
                            items=items,
                            claims=claim_mappings,
                            citations=citations,
                            calculations=calculations,
                            rules=rules,
                        ),
                        render_decision_form(model),
                        render_audit_details(model),
                    )
                ),
            ),
            _render_process_footer(model),
            "</div>",
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
