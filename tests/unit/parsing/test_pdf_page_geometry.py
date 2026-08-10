from pathlib import Path

import pytest

from ansim_review.parsing.pdf_page_geometry import read_pdf_page_geometries
from tests.helpers.pdf_fixtures import write_pdf_fixture


def test_cropbox_uses_size_difference_and_preserves_origin(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "crop.pdf",
        page_sizes=((600.0, 800.0),),
        crop_boxes={1: (10.0, 20.0, 510.0, 720.0)},
    )
    page = read_pdf_page_geometries(source)[0]
    assert page.box_kind == "CROP_BOX"
    assert (page.origin_x, page.origin_y) == (10.0, 20.0)
    assert (page.width, page.height) == (500.0, 700.0)


def test_missing_cropbox_uses_mediabox(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "media.pdf",
        page_sizes=((842.0, 1191.0),),
    )
    page = read_pdf_page_geometries(source)[0]
    assert page.box_kind == "MEDIA_BOX"
    assert (page.width, page.height) == (842.0, 1191.0)


def test_invalid_cropbox_falls_back_to_mediabox(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "invalid-crop.pdf",
        page_sizes=((1000.0, 700.0),),
        crop_boxes={1: (0.0, 0.0, 0.0, 0.0)},
    )
    page = read_pdf_page_geometries(source)[0]
    assert page.box_kind == "MEDIA_BOX"
    assert (page.width, page.height) == (1000.0, 700.0)


def test_mixed_sizes_and_negative_rotation_are_normalized(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "mixed.pdf",
        page_sizes=((595.0, 842.0), (1191.0, 842.0)),
        rotations={2: -90},
    )
    pages = read_pdf_page_geometries(source)
    assert [(page.width, page.height) for page in pages] == [
        (595.0, 842.0),
        (1191.0, 842.0),
    ]
    assert [page.rotation for page in pages] == [0, 270]


def test_non_quarter_turn_rotation_is_rejected(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "bad-rotation.pdf",
        page_sizes=((600.0, 800.0),),
        rotations={1: 45},
    )
    with pytest.raises(ValueError, match="PAGE_ROTATION_INVALID"):
        read_pdf_page_geometries(source)


def test_unreadable_pdf_has_explicit_reason(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not-a-pdf")
    with pytest.raises(ValueError, match="PAGE_DIMENSIONS_UNAVAILABLE"):
        read_pdf_page_geometries(source)


def test_inherited_cropbox_is_used_as_canonical_geometry(tmp_path: Path) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, RectangleObject

    source = tmp_path / "inherited-crop.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=600.0, height=800.0)
    if "/CropBox" in page:
        del page["/CropBox"]
    writer._pages.get_object()[NameObject("/CropBox")] = RectangleObject(
        (10.0, 20.0, 510.0, 720.0)
    )
    with source.open("wb") as stream:
        writer.write(stream)

    geometry = read_pdf_page_geometries(source)[0]

    assert geometry.box_kind == "CROP_BOX"
    assert (geometry.origin_x, geometry.origin_y) == (10.0, 20.0)
    assert (geometry.width, geometry.height) == (500.0, 700.0)
