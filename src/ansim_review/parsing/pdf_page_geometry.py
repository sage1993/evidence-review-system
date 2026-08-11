from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

from pypdf import PageObject, PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import RectangleObject

PageBoxKind = Literal["CROP_BOX", "MEDIA_BOX"]


@dataclass(frozen=True, slots=True)
class PdfPageGeometry:
    page_number: int
    width: float
    height: float
    box_kind: PageBoxKind
    origin_x: float
    origin_y: float
    rotation: int


def _validated_rectangle(
    rectangle: RectangleObject,
) -> tuple[float, float, float, float] | None:
    values = (
        float(rectangle.left),
        float(rectangle.bottom),
        float(rectangle.right),
        float(rectangle.top),
    )
    if not all(isfinite(value) for value in values):
        return None
    left, bottom, right, top = values
    if right <= left or top <= bottom:
        return None
    return values


def _resolved_rectangle(
    page: PageObject,
    *,
    key: str,
    attribute: str,
) -> tuple[float, float, float, float] | None:
    if key == "/CropBox" and page.get(key) is None:
        return None
    try:
        rectangle = getattr(page, attribute)
        if not isinstance(rectangle, RectangleObject):
            rectangle = RectangleObject(rectangle)
        return _validated_rectangle(rectangle)
    except (PdfReadError, TypeError, ValueError, IndexError):
        return None


def _normalized_rotation(page: PageObject, page_number: int) -> int:
    value = page.get("/Rotate", 0)
    if hasattr(value, "get_object"):
        value = value.get_object()
    if isinstance(value, bool) or not isinstance(value, int) or value % 90 != 0:
        raise ValueError(f"PAGE_ROTATION_INVALID: page {page_number}")
    return int(value) % 360


def read_pdf_page_geometries(source_path: Path) -> tuple[PdfPageGeometry, ...]:
    try:
        reader = PdfReader(source_path)
        pages = tuple(reader.pages)
    except (
        OSError,
        PdfReadError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ) as error:
        raise ValueError(
            f"PAGE_DIMENSIONS_UNAVAILABLE: unable to read {source_path.name}"
        ) from error
    if not pages:
        raise ValueError("PAGE_DIMENSIONS_UNAVAILABLE: PDF contains no pages")

    result: list[PdfPageGeometry] = []
    for page_number, page in enumerate(pages, start=1):
        rotation = _normalized_rotation(page, page_number)
        crop = _resolved_rectangle(page, key="/CropBox", attribute="cropbox")
        media = _resolved_rectangle(page, key="/MediaBox", attribute="mediabox")
        selected = crop if crop is not None else media
        if selected is None:
            raise ValueError(f"PAGE_DIMENSIONS_UNAVAILABLE: page {page_number}")
        left, bottom, right, top = selected
        result.append(
            PdfPageGeometry(
                page_number=page_number,
                width=right - left,
                height=top - bottom,
                box_kind="CROP_BOX" if crop is not None else "MEDIA_BOX",
                origin_x=left,
                origin_y=bottom,
                rotation=rotation,
            )
        )
    return tuple(result)
