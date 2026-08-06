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


@dataclass(frozen=True, slots=True)
class _PageAsset:
    data_uri: str
    pdf_width: float
    pdf_height: float


@dataclass(frozen=True, slots=True)
class _CitationRender:
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
    if set(metadata) != required:
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
    return _PageAsset(
        data_uri="data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii"),
        pdf_width=pdf_width,
        pdf_height=pdf_height,
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
    """Read and verify each cited page once before rendering citations."""
    assets: dict[tuple[str, int, str], tuple[str, _PageAsset]] = {}
    for claim_value in claims:
        claim = _mapping(claim_value, "claim")
        for citation_value in _sequence(claim.get("citations", []), "citations"):
            citation = _mapping(citation_value, "citation")
            identity = _citation_identity(citation)
            if identity not in assets:
                revision_id, page_number, source_hash = identity
                assets[identity] = (
                    f"page-{len(assets) + 1}",
                    _verified_page_image(
                        page_root,
                        revision_id,
                        page_number,
                        source_hash,
                    ),
                )
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
    rect_y = page_asset.pdf_height - top
    bbox_text = ",".join(str(item) for item in (left, bottom, right, top))
    citation_id = citation.get("citation_id")
    metadata_html = "".join(
        (
            '<article class="citation" ',
            f'data-asset-key="{_text(asset_key)}" ',
            f'data-citation-id="{_text(citation_id)}" ',
            f'data-bbox="{_text(bbox_text)}">',
            f"<h4>{_text(citation.get('title'))}</h4>",
            '<p class="citation-location"><strong>',
            f"{_text(citation.get('document_id'))} · page {page_number}</strong></p>",
            f"<p>Revision {_text(revision_id)}</p>",
            f"<blockquote>{_text(citation.get('quote'))}</blockquote>",
            '<dl class="provenance">',
            f"<dt>Citation ID</dt><dd><code>{_text(citation_id)}</code></dd>",
            f"<dt>Evidence ID</dt><dd><code>{_text(citation.get('evidence_id'))}</code></dd>",
            f"<dt>BBox</dt><dd><code>{_text(bbox_text)}</code></dd>",
            f"<dt>Geometry</dt><dd><code>{_display_value(citation.get('geometry', bbox_text))}"
            "</code></dd>",
            f"<dt>Source SHA-256</dt><dd><code>{_text(source_hash)}</code></dd>",
            "</dl>",
            '<button class="evidence-link" type="button" ',
            f'data-asset-key="{_text(asset_key)}">Focus cited page</button>',
            "</article>",
        )
    )
    overlay_html = "".join(
        (
            f'<svg viewBox="0 0 {page_asset.pdf_width} {page_asset.pdf_height}" ',
            'class="citation-overlay" ',
            f'data-asset-key="{_text(asset_key)}" ',
            'preserveAspectRatio="none" aria-label="citation bbox overlay">',
            f'<rect x="{left}" y="{rect_y}" width="{right - left}" ',
            f'height="{top - bottom}"></rect>',
            "</svg>",
        )
    )
    return _CitationRender(metadata_html=metadata_html, overlay_html=overlay_html)


def _table_rows(items: Sequence[object], columns: tuple[str, ...]) -> str:
    rows: list[str] = []
    for item in items:
        row = _mapping(item, "table row")
        cells = "".join(f"<td>{_display_value(row.get(column))}</td>" for column in columns)
        rows.append("<tr>" + cells + "</tr>")
    return "".join(rows) or f'<tr><td colspan="{len(columns)}">Not available</td></tr>'


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
    return "".join(
        (
            '<header id="review-status" class="status-band">',
            '<p class="eyebrow">Evidence Review Workspace</p>',
            f"<h1>{_text(model.get('run_id'))}</h1>",
            f'<p class="status-value">{_text(model.get("status"))}</p>',
            '<p class="warning">Machine evaluation is not the final decision.</p>',
            "</header>",
        )
    )


def _render_summary(model: Mapping[str, object]) -> str:
    summary = _mapping(model.get("summary", {}), "summary")
    audit = _mapping(model.get("audit", {}), "audit")
    return "".join(
        (
            '<section id="review-summary" aria-labelledby="summary-heading">',
            '<h2 id="summary-heading">Review summary</h2>',
            f"<p>{_text(model.get('question'))}</p>",
            '<dl class="summary-grid">',
            f"<div><dt>Citations</dt><dd>{_display_value(summary.get('citation_count'))}"
            "</dd></div>",
            f"<div><dt>Calculations</dt><dd>{_display_value(summary.get('calculation_count'))}"
            "</dd></div>",
            f"<div><dt>Approved rules</dt><dd>{_display_value(summary.get('approved_rule_count'))}"
            "</dd></div>",
            f"<div><dt>Missing inputs</dt><dd>{_display_value(summary.get('missing_input_count'))}"
            "</dd></div>",
            f"<div><dt>Uncited claims</dt><dd>{_display_value(audit.get('uncited_count'))}"
            "</dd></div>",
            "</dl>",
            '<section id="ready-for-review"><h3>Ready for review</h3>',
            f"<p>{_text(model.get('status'))}</p></section>",
            '<section id="abstention-reasons"><h3>Abstain or seek more evidence</h3><ul>',
            "".join(
                f"<li>{_text(reason)}</li>"
                for reason in _sequence(model.get("abstention_reasons", []), "abstention_reasons")
            )
            or "<li>None recorded.</li>",
            "</ul></section>",
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
            '<nav id="review-items" aria-label="Review items">',
            "<h2>Review items</h2>",
            "".join(buttons) or "<p>No review items are available.</p>",
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
                    '<div class="page-canvas">',
                    f'<img alt="Verified page {page_number}" src="{asset.data_uri}">',
                    '<div class="overlay-layer">',
                    "".join(overlays.get(asset_key, [])),
                    "</div>",
                    "</div>",
                    "<figcaption>Revision ",
                    _text(revision_id),
                    " · page ",
                    str(page_number),
                    " · source SHA-256 <code>",
                    _text(source_hash),
                    "</code></figcaption></figure>",
                )
            )
        )
    return "".join(
        (
            '<section id="evidence-viewer" aria-labelledby="evidence-heading">',
            '<div class="viewer-heading"><h2 id="evidence-heading">Evidence viewer</h2>',
            '<label>Zoom <input id="evidence-zoom" type="range" min="1" max="2" '
            'step="0.1" value="1"></label></div>',
            "".join(pages) or "<p>No verified page image is cited.</p>",
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
    citations: Mapping[str, Sequence[str]],
    calculations: Sequence[object],
    rules: Sequence[object],
) -> str:
    panels: list[str] = []
    for index, item in enumerate(items):
        claim = _claim_for_item(item, claims)
        claim_html = "<p>No claim record is available.</p>"
        citation_html = "<p>No citation is available.</p>"
        if claim is not None:
            claim_html = f"<p>{_text(claim.get('text'))}</p>"
            citation_html = "".join(citations.get(_text(claim.get("claim_id")), []))
        panels.append(
            "".join(
                (
                    '<article class="detail-panel',
                    " is-selected" if index == 0 else "",
                    f'" data-item-id="{_text(item.get("item_id"))}">',
                    "<h3>Item ",
                    _text(item.get("item_id")),
                    '</h3><dl class="item-summary">',
                    f"<div><dt>Claim</dt><dd>{_text(item.get('claim_id'))}</dd></div>",
                    f"<div><dt>Status</dt><dd>{_text(item.get('status'))}</dd></div>",
                    f"<div><dt>Completeness</dt><dd>{_text(item.get('completeness'))}</dd></div>",
                    "</dl>",
                    '<section data-tab-panel="evidence">',
                    "<h4>Claim and evidence</h4>",
                    claim_html,
                    citation_html,
                    "</section>",
                    '<section data-tab-panel="calculations" hidden>',
                    "<h4>Recorded calculations</h4><table><thead><tr><th>ID</th>",
                    "<th>Formula</th><th>Version</th><th>Substitution</th><th>Result</th>",
                    "<th>Comparison</th></tr></thead><tbody>",
                    _table_rows(
                        calculations,
                        (
                            "calculation_result_id",
                            "formula_id",
                            "formula_version",
                            "substitution",
                            "display_result",
                            "comparison",
                        ),
                    ),
                    "</tbody></table></section>",
                    '<section data-tab-panel="rules" hidden>',
                    "<h4>Recorded rule evaluations</h4><table><thead><tr><th>Rule</th>",
                    "<th>Version</th><th>Status</th></tr></thead><tbody>",
                    _table_rows(rules, ("rule_id", "rule_version", "status")),
                    "</tbody></table></section>",
                    "</article>",
                )
            )
        )
    return "".join(
        (
            '<section id="detail-tabs" aria-labelledby="detail-heading">',
            '<h2 id="detail-heading">Item detail</h2>',
            '<div role="tablist" aria-label="Item detail sections">',
            '<button type="button" role="tab" aria-selected="true" '
            'data-detail-tab="evidence">Evidence</button>',
            '<button type="button" role="tab" aria-selected="false" '
            'data-detail-tab="calculations">Calculations</button>',
            '<button type="button" role="tab" aria-selected="false" '
            'data-detail-tab="rules">Rule evaluations</button>',
            "</div>",
            "".join(panels) or "<p>Select a review item to inspect its evidence.</p>",
            "</section>",
        )
    )


def _render_decision_form(model: Mapping[str, object]) -> str:
    decision = _mapping(model.get("decision", {}), "decision")
    options = _sequence(decision.get("allowed_values", []), "decision.allowed_values")
    option_html = "".join(
        f'<option value="{_text(option)}">{_text(option)}</option>' for option in options
    )
    return "".join(
        (
            '<section id="decision-form" aria-labelledby="decision-heading">',
            '<h2 id="decision-heading">Human decision</h2>',
            "<p>The machine packet remains read-only. This form creates a separate "
            "reviewer envelope.</p>",
            '<form action="./decision" method="post">',
            '<label>Reviewer ID <input name="reviewer_id" autocomplete="name" required></label>',
            '<label>Reviewed at (ISO-8601 with timezone) <input name="reviewed_at" ',
            'placeholder="2026-08-07T10:30:00+09:00" required></label>',
            '<label>Decision <select name="decision" required>',
            '<option value="" selected disabled>Select a decision</option>',
            option_html,
            "</select></label>",
            '<label>Notes <textarea name="notes" rows="4"></textarea></label>',
            f'<input name="packet_sha256" type="hidden" '
            f'value="{_text(decision.get("packet_sha256"))}">',
            '<div class="decision-actions"><button type="submit">Submit decision</button>',
            '<button type="button" data-download-decision>Download decision '
            "envelope</button></div>",
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
    citations: dict[str, list[str]] = {}
    overlays: dict[str, list[str]] = {}
    claim_mappings: list[Mapping[str, object]] = []
    for claim_value in claims:
        claim = _mapping(claim_value, "claim")
        claim_mappings.append(claim)
        claim_id = _text(claim.get("claim_id"))
        citations[claim_id] = []
        for citation_value in _sequence(claim.get("citations", []), "citations"):
            citation = _mapping(citation_value, "citation")
            asset_key, asset = assets[_citation_identity(citation)]
            rendered = _citation_render(
                citation,
                asset_key=asset_key,
                page_asset=asset,
            )
            citations[claim_id].append(rendered.metadata_html)
            overlays.setdefault(asset_key, []).append(rendered.overlay_html)
    items = _review_items(model, claims)
    calculations = _sequence(model.get("calculations", []), "calculations")
    rules = _sequence(model.get("rules", []), "rules")
    return "".join(
        (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_text(model.get('run_id'))} Review Workspace</title><style>{css}</style>",
            "</head><body>",
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
            ),
            _render_decision_form(model),
            "</main>",
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
