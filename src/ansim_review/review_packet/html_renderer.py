"""Self-contained, print-safe reviewer HTML rendering."""
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
        raise FileNotFoundError(
            f"verified page image missing: {revision_id} page {page_number}"
        )

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
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return _PageAsset(
        data_uri="data:image/png;base64," + encoded,
        pdf_width=pdf_width,
        pdf_height=pdf_height,
    )


def _citation_html(value: object, page_root: Path) -> str:
    citation = _mapping(value, "citation")
    revision_id = str(citation.get("revision_id", ""))
    page_number = _page_number(citation.get("page_number"))
    source_hash = str(citation.get("source_hash", ""))
    bbox_values = _bbox(citation.get("bbox", []))
    left, bottom, right, top = bbox_values
    bbox_text = ",".join(str(item) for item in bbox_values)
    page_asset = _verified_page_image(
        page_root,
        revision_id,
        page_number,
        source_hash,
    )
    if (
        left < 0
        or bottom < 0
        or right > page_asset.pdf_width
        or top > page_asset.pdf_height
    ):
        raise ValueError("citation bbox is outside the verified page bounds")
    rect_width = right - left
    rect_height = top - bottom
    rect_y = page_asset.pdf_height - top
    image_html = (
        '<div class="page">'
        f'<img alt="cited page" src="{page_asset.data_uri}">'
        f'<svg viewBox="0 0 {page_asset.pdf_width} {page_asset.pdf_height}" '
        'preserveAspectRatio="none" aria-label="bbox overlay">'
        f'<rect x="{left}" y="{rect_y}" width="{rect_width}" '
        f'height="{rect_height}"></rect>'
        "</svg></div>"
    )
    return (
        f'<article class="evidence" data-bbox="{escape(bbox_text, quote=True)}">'
        "<div>"
        f'<h3>{_text(citation.get("title"))}</h3>'
        f'<p><strong>{_text(citation.get("document_id"))} · page '
        f"{page_number}</strong></p>"
        f'<blockquote>{_text(citation.get("quote"))}</blockquote>'
        f'<p><code>{_text(citation.get("evidence_id"))}</code> · bbox '
        f"{escape(bbox_text)}</p>"
        f'<p>source SHA-256: <code>{_text(citation.get("source_hash"))}</code></p>'
        "</div>" + image_html + "</article>"
    )


def _table_rows(items: Sequence[object], columns: tuple[str, ...]) -> str:
    rows: list[str] = []
    for item in items:
        row = _mapping(item, "table row")
        cells = "".join(f"<td>{_text(row.get(column))}</td>" for column in columns)
        rows.append("<tr>" + cells + "</tr>")
    return "".join(rows)


def render_review_html(
    view_model: Mapping[str, object], page_image_root: Path
) -> str:
    """Render a single-file reviewer packet without editable machine fields."""
    model = _mapping(view_model, "view_model")
    css_path = Path(__file__).with_name("assets") / "review.css"
    css = css_path.read_text(encoding="utf-8")
    claims_html: list[str] = []
    for value in _sequence(model.get("claims", []), "claims"):
        claim = _mapping(value, "claim")
        citations = "".join(
            _citation_html(citation, page_image_root)
            for citation in _sequence(claim.get("citations", []), "citations")
        )
        claims_html.append(
            f'<section><h2>Claim {_text(claim.get("claim_id"))}</h2>'
            f'<p>{_text(claim.get("text"))}</p>{citations}</section>'
        )
    calculations = _sequence(model.get("calculations", []), "calculations")
    rules = _sequence(model.get("rules", []), "rules")
    confidence_value = model.get("confidence")
    confidence_html = "<p>Not available</p>"
    if confidence_value is not None:
        confidence = _mapping(confidence_value, "confidence")
        factors = _sequence(confidence.get("factors", []), "confidence.factors")
        confidence_html = (
            f'<p>Level: <strong>{_text(confidence.get("level"))}</strong> · '
            f'score {_text(confidence.get("score"))}</p>'
            "<table><thead><tr><th>Factor</th><th>Value</th><th>Weight</th>"
            "<th>Contribution</th><th>Source</th></tr></thead><tbody>"
            + _table_rows(
                factors,
                ("name", "value", "weight", "contribution", "source"),
            )
            + "</tbody></table>"
        )
    reasons = _sequence(model.get("abstention_reasons", []), "abstention_reasons")
    return "".join(
        (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            f"<title>{_text(model.get('run_id'))}</title><style>{css}</style>",
            "</head><body>",
            f'<h1>Evidence Review Packet</h1><p class="status">'
            f"{_text(model.get('status'))}</p>",
            '<p class="warning">Machine evaluation is not the final decision</p>',
            f"<section><h2>Question</h2><p>{_text(model.get('question'))}</p>",
            "</section>",
            "".join(claims_html),
            "<section><h2>Math Engine</h2><table><thead><tr><th>ID</th>"
            "<th>Formula</th><th>Version</th><th>Substitution</th><th>Result</th>"
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
            "<section><h2>Rule Engine</h2><table><thead><tr><th>Rule</th>"
            "<th>Version</th><th>Status</th></tr></thead><tbody>",
            _table_rows(rules, ("rule_id", "rule_version", "status")),
            "</tbody></table></section>",
            f"<section><h2>Confidence</h2>{confidence_html}</section>",
            "<section><h2>Exceptions and conflicts</h2><p>Exceptions: ",
            _text(
                ", ".join(
                    str(item)
                    for item in _sequence(model.get("exceptions", []), "exceptions")
                )
            ),
            "</p><p>Conflicts: ",
            _text(
                ", ".join(
                    str(item)
                    for item in _sequence(model.get("conflicts", []), "conflicts")
                )
            ),
            "</p></section>",
            "<section><h2>Abstention reasons</h2><ul>",
            "".join(f"<li>{_text(reason)}</li>" for reason in reasons),
            "</ul></section>",
            "<section><h2>Human decision</h2><p>Blank. Record the reviewer "
            "decision in a separate append-only decision file.</p></section>",
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
