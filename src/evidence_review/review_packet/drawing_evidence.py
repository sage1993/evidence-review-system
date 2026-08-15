"""Self-contained Review Packet v2 drawing-evidence rendering."""

from __future__ import annotations

import base64
import math
from collections.abc import Mapping
from html import escape
from typing import cast

from evidence_review.contracts.review_v2 import (
    ReviewPacketV2,
    decode_review_packet_v2,
    review_packet_v2_document,
)
from evidence_review.contracts.validation import expect_int

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/tiff"}


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _coordinates(candidate: Mapping[str, object]) -> tuple[str, str, object]:
    geometry = _mapping(candidate.get("geometry"), "drawing.geometry")
    geometry_type = geometry.get("type")
    coordinate_system = geometry.get("coordinate_system")
    coordinates = geometry.get("coordinates")
    if not isinstance(geometry_type, str) or not isinstance(coordinate_system, str):
        raise ValueError("drawing geometry type and coordinate_system are required")
    return geometry_type, coordinate_system, coordinates


def _shape(candidate: Mapping[str, object], width: float, height: float) -> str:
    geometry_type, coordinate_system, raw = _coordinates(candidate)
    transform = (
        f' transform="translate(0 {height:g}) scale(1 -1)"'
        if coordinate_system == "PDF_BOTTOM_LEFT_POINTS"
        else ""
    )
    if geometry_type == "POINT":
        values = raw if isinstance(raw, list) else ()
        if len(values) != 2:
            raise ValueError("POINT coordinates are invalid")
        x, y = (_number(values[index], "POINT coordinate") for index in range(2))
        return f'<circle cx="{x:g}" cy="{y:g}" r="6"{transform}/>'
    if geometry_type == "BBOX":
        values = raw if isinstance(raw, list) else ()
        if len(values) != 4:
            raise ValueError("BBOX coordinates are invalid")
        left, bottom, right, top = (
            _number(values[index], "BBOX coordinate") for index in range(4)
        )
        return (
            f'<rect x="{left:g}" y="{bottom:g}" width="{right - left:g}" '
            f'height="{top - bottom:g}"{transform}/>'
        )
    if geometry_type in {"LINESTRING", "POLYGON"}:
        values = raw if isinstance(raw, list) else ()
        points = " ".join(
            f"{_number(point[0], 'path x'):g},{_number(point[1], 'path y'):g}"
            for point in values
            if isinstance(point, list) and len(point) == 2
        )
        if not points:
            raise ValueError("path geometry coordinates are invalid")
        tag = "polyline" if geometry_type == "LINESTRING" else "polygon"
        return f'<{tag} points="{points}"{transform}/>'
    raise ValueError(f"unsupported drawing geometry: {geometry_type}")


def _packet_document(packet: ReviewPacketV2 | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(packet, ReviewPacketV2):
        return _mapping(review_packet_v2_document(packet), "review_packet")
    return _mapping(
        review_packet_v2_document(decode_review_packet_v2(packet)),
        "review_packet",
    )


def _display_metadata_document(value: Mapping[str, object]) -> Mapping[str, object]:
    required = {
        "source_document", "candidate_id", "confirmation_id", "calibration_id",
        "reviewer", "confirmed_at", "calibration", "artifact_paths",
    }
    if set(value) != required:
        raise ValueError("display_metadata keys are invalid")
    source = _mapping(value["source_document"], "display_metadata.source_document")
    if set(source) != {"document_id", "revision_id", "page", "source_sha256"}:
        raise ValueError("display_metadata.source_document keys are invalid")
    calibration = _mapping(value["calibration"], "display_metadata.calibration")
    if set(calibration) != {
        "axis", "pixel_points", "real_length", "unit", "scale_x", "scale_y",
        "formula_id", "formula_version", "calculation_result_hash",
    }:
        raise ValueError("display_metadata.calibration keys are invalid")
    paths = _mapping(value["artifact_paths"], "display_metadata.artifact_paths")
    if set(paths) != {"candidate", "confirmation", "calibration"}:
        raise ValueError("display_metadata.artifact_paths keys are invalid")
    def contains_external(item: object) -> bool:
        if isinstance(item, str):
            return "http://" in item or "https://" in item
        if isinstance(item, Mapping):
            return any(contains_external(child) for child in item.values())
        if isinstance(item, list):
            return any(contains_external(child) for child in item)
        return False

    if contains_external(value):
        raise ValueError("display_metadata cannot contain external URLs")
    return value


def render_drawing_evidence(
    packet: ReviewPacketV2 | Mapping[str, object],
    *,
    page_images: Mapping[int, bytes],
    page_dimensions: Mapping[int, tuple[float, float]],
    mime: str = "image/png",
    display_metadata: Mapping[str, object] | None = None,
) -> str:
    """Render validated drawing evidence without external resources."""
    if mime not in _ALLOWED_MIME:
        raise ValueError("unsupported page image MIME")
    document = _packet_document(packet)
    metadata = (
        None
        if display_metadata is None
        else _display_metadata_document(display_metadata)
    )
    raw_candidates = document.get("drawing_evidence")
    if not isinstance(raw_candidates, list):
        raise ValueError("drawing_evidence must be an array")
    candidates = tuple(_mapping(item, "drawing_evidence item") for item in raw_candidates)
    pages = sorted({expect_int(candidate["page"], "drawing.page") for candidate in candidates})
    for page in pages:
        if page not in page_images or page not in page_dimensions:
            raise ValueError(f"missing page asset or dimensions: {page}")
        width, height = page_dimensions[page]
        if width <= 0 or height <= 0:
            raise ValueError("page dimensions must be positive")

    sections: list[str] = []
    for page in pages:
        width, height = page_dimensions[page]
        image = base64.b64encode(page_images[page]).decode("ascii")
        overlays: list[str] = []
        rows: list[str] = []
        for candidate in candidates:
            if candidate.get("page") != page:
                continue
            candidate_id = escape(str(candidate.get("candidate_id", "")), quote=True)
            candidate_type = escape(str(candidate.get("candidate_type", "")))
            source_hash = escape(str(candidate.get("source_sha256", "")))
            status = escape(str(candidate.get("status", "")))
            origin = escape(str(candidate.get("origin", "")))
            overlays.append(
                f'<g data-candidate-id="{candidate_id}" '
                f'data-origin="{origin}" data-status="{status}">'
                f"{_shape(candidate, width, height)}</g>"
            )
            rows.append(
                f"<tr><td>{candidate_id}</td><td>{candidate_type}</td>"
                f"<td>{status}</td><td>{origin}</td><td>{source_hash}</td>"
                f"<td>{page}</td></tr>"
            )
        sections.append(
            f'<section data-page="{page}"><h2>Drawing page {page}</h2>'
            f'<div class="drawing-canvas" style="aspect-ratio:{width:g}/{height:g}">'
            f'<img alt="drawing page {page}" src="data:{mime};base64,{image}"/>'
            f'<svg viewBox="0 0 {width:g} {height:g}" '
            f'aria-label="drawing evidence overlay">{"".join(overlays)}</svg></div>'
            '<table><thead><tr><th>Candidate</th><th>Type</th><th>Status</th>'
            '<th>Origin</th><th>Source SHA-256</th><th>Page</th></tr></thead><tbody>'
            f'{"".join(rows)}</tbody></table></section>'
        )
    human_decision_value = document.get("human_decision")
    human_decision = (
        "null"
        if human_decision_value is None
        else escape(str(human_decision_value))
    )
    metadata_html = ""
    if metadata is not None:
        source = _mapping(metadata["source_document"], "display_metadata.source_document")
        calibration = _mapping(metadata["calibration"], "display_metadata.calibration")
        paths = _mapping(metadata["artifact_paths"], "display_metadata.artifact_paths")
        metadata_html = (
            "<section><h2>Verified handoff metadata</h2>"
            f"<p>Document: {escape(str(source['document_id']))} / "
            f"{escape(str(source['revision_id']))}</p>"
            f"<p>Candidate: <code>{escape(str(metadata['candidate_id']))}</code></p>"
            f"<p>Confirmation: <code>{escape(str(metadata['confirmation_id']))}</code></p>"
            f"<p>Calibration: <code>{escape(str(metadata['calibration_id']))}</code></p>"
            f"<p>Reviewer: {escape(str(metadata['reviewer']))}; "
            f"confirmed_at: {escape(str(metadata['confirmed_at']))}</p>"
            f"<p>Calibration: {escape(str(calibration['axis']))} / "
            f"{escape(str(calibration['real_length']))} {escape(str(calibration['unit']))}; "
            f"formula: {escape(str(calibration['formula_id']))} "
            f"{escape(str(calibration['formula_version']))}</p>"
            f"<p>Artifacts: {escape(str(paths['candidate']))}; "
            f"{escape(str(paths['confirmation']))}; "
            f"{escape(str(paths['calibration']))}</p>"
            "</section>"
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<title>Review Packet v2 drawing evidence</title>'
        '<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#172033}'
        'section{margin:2rem 0} .drawing-canvas{position:relative;max-width:100%}'
        '.drawing-canvas img,.drawing-canvas svg{position:absolute;inset:0;width:100%;height:100%}'
        'svg{pointer-events:none}svg g{fill:none;stroke:#c62828;stroke-width:2}'
        'table{border-collapse:collapse}th,td{border:1px solid #ccd2db;padding:.35rem}</style>'
        '</head><body><h1>Review Packet v2</h1>'
        f'<p>Run: {escape(str(document.get("run_id")))}</p>'
        f'<p>Case: {escape(str(document.get("case_id")))}</p>'
        f'<p>human_decision: {human_decision}</p>'
        f"{metadata_html}"
        f'{"".join(sections)}</body></html>'
    )


__all__ = ["render_drawing_evidence"]
