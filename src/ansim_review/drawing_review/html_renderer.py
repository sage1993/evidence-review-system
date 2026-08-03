"""Self-contained SVG renderer for reviewer drawing annotation."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Literal, cast

CoordinateSystem = Literal["PDF_BOTTOM_LEFT_POINTS", "IMAGE_TOP_LEFT_PIXELS"]

_ALLOWED_IMAGE_MIMES = ("image/png", "image/jpeg")
_COORDINATE_SYSTEMS: tuple[CoordinateSystem, ...] = (
    "PDF_BOTTOM_LEFT_POINTS",
    "IMAGE_TOP_LEFT_PIXELS",
)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_text(value: object) -> str:
    return "" if value is None else str(value)


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")
    return result


def _positive_number(value: object, field: str) -> float:
    result = _number(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _coordinate_system(value: object, field: str) -> CoordinateSystem:
    candidate = _string(value, field)
    if candidate not in _COORDINATE_SYSTEMS:
        raise ValueError(f"unsupported {field}: {candidate}")
    return cast(CoordinateSystem, candidate)


def _position(value: object, field: str) -> tuple[float, float]:
    items = _sequence(value, field)
    if len(items) != 2:
        raise ValueError(f"{field} must contain two numbers")
    return (_number(items[0], f"{field}[0]"), _number(items[1], f"{field}[1]"))


def _display_position(
    position: tuple[float, float],
    page_height: float,
    coordinate_system: CoordinateSystem,
) -> tuple[float, float]:
    x, y = position
    if coordinate_system == "PDF_BOTTOM_LEFT_POINTS":
        return (x, page_height - y)
    return position


def _points_text(
    value: object,
    field: str,
    page_height: float,
    coordinate_system: CoordinateSystem,
) -> str:
    positions = tuple(
        _display_position(
            _position(item, f"{field}[{index}]"),
            page_height,
            coordinate_system,
        )
        for index, item in enumerate(_sequence(value, field))
    )
    if not positions:
        raise ValueError(f"{field} must not be empty")
    return " ".join(f"{x},{y}" for x, y in positions)


def _geometry_html(
    candidate_id: str,
    value: object,
    page_height: float,
    coordinate_system: CoordinateSystem,
) -> str:
    geometry = _mapping(value, "candidate.geometry")
    geometry_type = _string(geometry.get("type"), "candidate.geometry.type")
    geometry_coordinate_system = _coordinate_system(
        geometry.get("coordinate_system"),
        "candidate.geometry.coordinate_system",
    )
    if geometry_coordinate_system != coordinate_system:
        raise ValueError("candidate geometry coordinate system mismatch")
    coordinates = geometry.get("coordinates")
    candidate_attr = escape(candidate_id, quote=True)

    if geometry_type == "POINT":
        x, y = _display_position(
            _position(coordinates, "candidate.geometry.coordinates"),
            page_height,
            coordinate_system,
        )
        return (
            f'<circle data-candidate-id="{candidate_attr}" '
            'class="candidate-geometry candidate-point" '
            f'cx="{x}" cy="{y}" r="6"></circle>'
        )

    if geometry_type == "BBOX":
        items = _sequence(coordinates, "candidate.geometry.coordinates")
        if len(items) != 4:
            raise ValueError("BBOX requires four coordinates")
        left = _number(items[0], "candidate.geometry.coordinates[0]")
        first_y = _number(items[1], "candidate.geometry.coordinates[1]")
        right = _number(items[2], "candidate.geometry.coordinates[2]")
        second_y = _number(items[3], "candidate.geometry.coordinates[3]")
        if left > right or first_y > second_y:
            raise ValueError("BBOX coordinates are inverted")
        y = first_y
        if coordinate_system == "PDF_BOTTOM_LEFT_POINTS":
            y = page_height - second_y
        return (
            f'<rect data-candidate-id="{candidate_attr}" '
            'class="candidate-geometry" '
            f'x="{left}" y="{y}" width="{right - left}" '
            f'height="{second_y - first_y}"></rect>'
        )

    if geometry_type == "LINESTRING":
        points = _points_text(
            coordinates,
            "candidate.geometry.coordinates",
            page_height,
            coordinate_system,
        )
        return (
            f'<polyline data-candidate-id="{candidate_attr}" '
            'class="candidate-geometry" fill="none" '
            f'points="{escape(points, quote=True)}"></polyline>'
        )

    if geometry_type == "POLYGON":
        points = _points_text(
            coordinates,
            "candidate.geometry.coordinates",
            page_height,
            coordinate_system,
        )
        return (
            f'<polygon data-candidate-id="{candidate_attr}" '
            'class="candidate-geometry" '
            f'points="{escape(points, quote=True)}"></polygon>'
        )

    raise ValueError(f"unsupported candidate geometry type: {geometry_type}")


def _candidate_button(value: object) -> str:
    candidate = _mapping(value, "candidate")
    candidate_id = _string(candidate.get("candidate_id"), "candidate.candidate_id")
    candidate_type = _string(candidate.get("candidate_type"), "candidate.candidate_type")
    origin = _string(candidate.get("origin"), "candidate.origin")
    status = _string(candidate.get("status"), "candidate.status")
    raw_value = _optional_text(candidate.get("raw_value"))
    normalized = _optional_text(candidate.get("normalized_candidate"))
    display_value = normalized or raw_value
    return (
        "<li>"
        '<button type="button" data-candidate-button '
        f'data-candidate-id="{escape(candidate_id, quote=True)}" '
        f'data-candidate-type="{escape(candidate_type, quote=True)}" '
        f'data-candidate-origin="{escape(origin, quote=True)}" '
        f'data-candidate-status="{escape(status, quote=True)}" '
        f'data-candidate-value="{escape(display_value, quote=True)}" '
        'aria-pressed="false">'
        f"<strong>{escape(candidate_type)}</strong><br>"
        f"<code>{escape(candidate_id)}</code><br>"
        f"<span>{escape(display_value)}</span>"
        "</button></li>"
    )


def render_annotation_html(
    view_model: Mapping[str, object],
    page_image: bytes,
    mime: str,
) -> str:
    """Render one self-contained reviewer annotation workspace."""
    model = _mapping(view_model, "view_model")
    if model.get("format") != "evidence-review/drawing-review-view":
        raise ValueError("unsupported drawing review view format")
    if model.get("version") != 1:
        raise ValueError("unsupported drawing review view version")
    if mime not in _ALLOWED_IMAGE_MIMES:
        raise ValueError("unsupported image MIME")
    if not isinstance(page_image, bytes) or not page_image:
        raise ValueError("page image must contain bytes")

    page_width = _positive_number(model.get("page_width"), "page_width")
    page_height = _positive_number(model.get("page_height"), "page_height")
    coordinate_system = _coordinate_system(
        model.get("coordinate_system"),
        "coordinate_system",
    )
    source_sha256 = _string(model.get("source_sha256"), "source_sha256")
    page = model.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")

    candidates = _sequence(model.get("candidates"), "candidates")
    buttons: list[str] = []
    geometries: list[str] = []
    for value in candidates:
        candidate = _mapping(value, "candidate")
        candidate_id = _string(candidate.get("candidate_id"), "candidate.candidate_id")
        buttons.append(_candidate_button(candidate))
        geometries.append(
            _geometry_html(
                candidate_id,
                candidate.get("geometry"),
                page_height,
                coordinate_system,
            )
        )

    asset_root = Path(__file__).with_name("assets")
    css = (asset_root / "annotation.css").read_text(encoding="utf-8")
    javascript = (asset_root / "annotation.js").read_text(encoding="utf-8")
    encoded = base64.b64encode(page_image).decode("ascii")
    image_uri = f"data:{mime};base64,{encoded}"

    return "".join(
        (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            "<title>Drawing annotation workspace</title>",
            f"<style>{css}</style></head><body>",
            "<header><h1>Drawing annotation workspace</h1>",
            f"<span>page {page} · <code>{escape(source_sha256)}</code></span></header>",
            '<div class="workspace">',
            '<aside class="panel"><p class="warning">Reviewer confirmation is required '</n            'before engine binding.</p><h2>Candidates</h2><ul class="candidate-list">',
            "".join(buttons),
            "</ul></aside>",
            '<main class="canvas-panel"><div class="page-canvas">',
            f'<img alt="verified drawing page" src="{image_uri}">',
            f'<svg viewBox="0 0 {page_width} {page_height}" '
            'preserveAspectRatio="none" aria-label="drawing candidate overlay">',
            "".join(geometries),
            "</svg></div></main>",
            '<aside class="panel detail-panel"><h2>Selected candidate</h2>',
            '<p>ID: <code data-detail-id></code></p>',
            '<p>Type: <span data-detail-type></span></p>',
            '<p>Origin: <span data-detail-origin></span></p>',
            '<p>Status: <span data-detail-status></span></p>',
            '<p class="detail-value" data-detail-value></p>',
            '<fieldset><legend>Reviewer action</legend>',
            '<label><input type="radio" name="review-action" value="ACCEPTED"> Accept</label>',
            '<label><input type="radio" name="review-action" value="REJECTED"> Reject</label>',
            '<label><input type="radio" name="review-action" value="EDITED"> Edit</label>',
            '<label><input type="radio" name="review-action" value="CREATED"> Create</label>',
            "</fieldset></aside></div>",
            f"<script>{javascript}</script></body></html>",
        )
    )
