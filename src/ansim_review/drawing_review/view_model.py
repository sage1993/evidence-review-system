"""Deterministic browser projection for verified drawing candidates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import cast

from ansim_review.contracts.drawing import (
    CoordinateSystem,
    DrawingCandidate,
    FlatCoordinates,
    PathCoordinates,
    decode_drawing_candidate,
    drawing_candidate_document,
    geometry_document,
)
from ansim_review.contracts.validation import expect_sha256

_COORDINATE_SYSTEMS: tuple[CoordinateSystem, ...] = (
    "PDF_BOTTOM_LEFT_POINTS",
    "IMAGE_TOP_LEFT_PIXELS",
)


@dataclass(frozen=True, slots=True)
class DrawingPage:
    """Verified drawing page bounds used by the browser projection."""

    source_sha256: str
    page: int
    coordinate_system: CoordinateSystem
    width: float
    height: float

    def __post_init__(self) -> None:
        expect_sha256(self.source_sha256, "source_sha256")
        if isinstance(self.page, bool) or self.page < 1:
            raise ValueError("page must be positive")
        if self.coordinate_system not in _COORDINATE_SYSTEMS:
            raise ValueError("coordinate_system is invalid")
        for field, value in (("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field} must be a positive finite number")
            if not isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{field} must be a positive finite number")


def _positions(candidate: DrawingCandidate) -> tuple[tuple[float, float], ...]:
    geometry = candidate.geometry
    if geometry.type == "POINT":
        coordinates = cast(FlatCoordinates, geometry.coordinates)
        return ((coordinates[0], coordinates[1]),)
    if geometry.type == "BBOX":
        coordinates = cast(FlatCoordinates, geometry.coordinates)
        left, first_y, right, second_y = coordinates
        return ((left, first_y), (right, second_y))
    return cast(PathCoordinates, geometry.coordinates)


def _validate_page_bounds(page: DrawingPage, candidate: DrawingCandidate) -> None:
    for x, y in _positions(candidate):
        if x < 0 or y < 0 or x > page.width or y > page.height:
            raise ValueError("candidate geometry is outside page bounds")


def _candidate_document(
    page: DrawingPage,
    candidate: DrawingCandidate,
) -> dict[str, object]:
    validated = decode_drawing_candidate(drawing_candidate_document(candidate))
    if validated.source_sha256 != page.source_sha256:
        raise ValueError("candidate source_sha256 does not match drawing page")
    if validated.page != page.page:
        raise ValueError("candidate page does not match drawing page")
    if validated.geometry.coordinate_system != page.coordinate_system:
        raise ValueError("candidate coordinate_system does not match drawing page")
    _validate_page_bounds(page, validated)
    return {
        "candidate_id": validated.candidate_id,
        "candidate_type": validated.candidate_type,
        "origin": validated.origin,
        "status": validated.status,
        "raw_value": validated.raw_value,
        "normalized_candidate": validated.normalized_candidate,
        "extractor": validated.extractor,
        "extractor_version": validated.extractor_version,
        "annotation_id": validated.annotation_id,
        "geometry": geometry_document(validated.geometry),
    }


def build_drawing_review_view_model(
    page: DrawingPage,
    candidates: Sequence[DrawingCandidate],
) -> dict[str, object]:
    """Build a stable JSON-compatible projection for one verified page."""
    documents = [_candidate_document(page, candidate) for candidate in candidates]
    documents.sort(key=lambda item: cast(str, item["candidate_id"]))
    return {
        "format": "evidence-review/drawing-review-view",
        "version": 1,
        "source_sha256": page.source_sha256,
        "page": page.page,
        "coordinate_system": page.coordinate_system,
        "page_width": float(page.width),
        "page_height": float(page.height),
        "candidates": documents,
    }
