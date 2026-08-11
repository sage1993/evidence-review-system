from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

PageSize = tuple[float, float]
PageBox = tuple[float, float, float, float]


def write_pdf_fixture(
    path: Path,
    *,
    page_sizes: Sequence[PageSize],
    crop_boxes: Mapping[int, PageBox] | None = None,
    rotations: Mapping[int, int] | None = None,
    metadata: Mapping[str, str] | None = None,
) -> Path:
    writer = PdfWriter()
    crops = crop_boxes or {}
    page_rotations = rotations or {}
    for page_number, (width, height) in enumerate(page_sizes, start=1):
        page = writer.add_blank_page(width=width, height=height)
        crop = crops.get(page_number)
        if crop is not None:
            page.cropbox = RectangleObject(crop)
        rotation = page_rotations.get(page_number)
        if rotation is not None:
            page[NameObject("/Rotate")] = NumberObject(rotation)
    if metadata:
        writer.add_metadata(dict(metadata))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        writer.write(stream)
    return path
