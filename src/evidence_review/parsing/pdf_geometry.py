"""Normalize parser bounding boxes into canonical PDF coordinates."""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from math import isfinite

from evidence_review.contracts.common import BBox


@dataclass(frozen=True, slots=True)
class PdfPageGeometry:
    """PDF page dimensions and source-box metadata from a parser."""

    width: float
    height: float
    origin_x: float = 0.0
    origin_y: float = 0.0
    rotation: int = 0
    box_kind: str = "MEDIA_BOX"

    def __post_init__(self) -> None:
        values = (self.width, self.height, self.origin_x, self.origin_y)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("page geometry values must be finite")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("page dimensions must be positive")
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be one of 0, 90, 180, 270")
        if self.box_kind not in {"CROP_BOX", "MEDIA_BOX"}:
            raise ValueError("box_kind must be CROP_BOX or MEDIA_BOX")

    def __iter__(self) -> Iterator[float]:
        yield self.width
        yield self.height

_TOLERANCE = 0.5


def _validated_numbers(raw_bbox: Sequence[float]) -> tuple[float, float, float, float]:
    if len(raw_bbox) != 4:
        raise ValueError("bbox must contain four numbers")
    values = tuple(float(value) for value in raw_bbox)
    if not all(isfinite(value) for value in values):
        raise ValueError("bbox values must be finite")
    left, bottom_or_top, right, top_or_bottom = values
    if left > right or bottom_or_top > top_or_bottom:
        raise ValueError("bbox coordinates are inverted")
    return left, bottom_or_top, right, top_or_bottom


def _clamp(value: float, maximum: float) -> float:
    if value < -_TOLERANCE or value > maximum + _TOLERANCE:
        raise ValueError("bbox is outside page bounds")
    return min(max(value, 0.0), maximum)


def _inverse_rotate(
    x: float,
    y: float,
    *,
    page_width: float,
    page_height: float,
    rotation: int,
) -> tuple[float, float]:
    if rotation == 0:
        return x, y
    if rotation == 90:
        return y, page_height - x
    if rotation == 180:
        return page_width - x, page_height - y
    if rotation == 270:
        return page_width - y, x
    raise ValueError("rotation must be one of 0, 90, 180, 270")


def normalize_bbox(
    raw_bbox: Sequence[float],
    source_system: str,
    page_width: float,
    page_height: float,
    *,
    rotation: int = 0,
) -> BBox:
    """Convert a parser bbox to left,bottom,right,top PDF points."""
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page dimensions must be positive")
    if rotation not in (0, 90, 180, 270):
        raise ValueError("rotation must be one of 0, 90, 180, 270")
    display_width, display_height = (
        (page_width, page_height) if rotation in (0, 180) else (page_height, page_width)
    )
    left, second, right, fourth = _validated_numbers(raw_bbox)
    left = _clamp(left, display_width)
    right = _clamp(right, display_width)

    if source_system == "TOP_LEFT":
        top_distance = _clamp(second, display_height)
        bottom_distance = _clamp(fourth, display_height)
        display_bottom = display_height - bottom_distance
        display_top = display_height - top_distance
    elif source_system == "PDF_BOTTOM_LEFT":
        display_bottom = _clamp(second, display_height)
        display_top = _clamp(fourth, display_height)
    else:
        raise ValueError(f"unsupported coordinate system: {source_system}")

    corners = (
        _inverse_rotate(
            x,
            y,
            page_width=page_width,
            page_height=page_height,
            rotation=rotation,
        )
        for x, y in (
            (left, display_bottom),
            (left, display_top),
            (right, display_bottom),
            (right, display_top),
        )
    )
    points = tuple(corners)
    xs = tuple(_clamp(point[0], page_width) for point in points)
    ys = tuple(_clamp(point[1], page_height) for point in points)
    return BBox(min(xs), min(ys), max(xs), max(ys))

def project_bbox_for_display(
    bbox: BBox,
    page_width: float,
    page_height: float,
    *,
    rotation: int = 0,
) -> BBox:
    """Project canonical bottom-left points into rotated display coordinates."""
    if rotation not in (0, 90, 180, 270):
        raise ValueError("rotation must be one of 0, 90, 180, 270")
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page dimensions must be positive")
    if rotation == 0:
        return bbox
    if rotation == 90:
        return BBox(
            page_height - bbox.top,
            bbox.left,
            page_height - bbox.bottom,
            bbox.right,
        )
    if rotation == 180:
        return BBox(
            page_width - bbox.right,
            page_height - bbox.top,
            page_width - bbox.left,
            page_height - bbox.bottom,
        )
    return BBox(
        bbox.bottom,
        page_width - bbox.right,
        bbox.top,
        page_width - bbox.left,
    )
