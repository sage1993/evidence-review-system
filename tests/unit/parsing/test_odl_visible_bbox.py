import pytest

from evidence_review.parsing.odl_source import normalize_odl_pdf_bbox
from evidence_review.parsing.pdf_page_geometry import PdfPageGeometry


def _a4_page() -> PdfPageGeometry:
    return PdfPageGeometry(
        page_number=1,
        width=595.0,
        height=841.0,
        box_kind="MEDIA_BOX",
        origin_x=0.0,
        origin_y=0.0,
        rotation=0,
    )


def test_odl_partially_off_page_bbox_is_clipped_to_visible_page() -> None:
    bbox = normalize_odl_pdf_bbox(
        (70.882, 633.986, 781.02, 670.546),
        _a4_page(),
    )

    assert bbox == [70.882, 633.986, 595.0, 670.546]


def test_odl_fully_off_page_bbox_remains_rejected() -> None:
    with pytest.raises(ValueError, match="bbox is outside page bounds"):
        normalize_odl_pdf_bbox(
            (600.0, 100.0, 700.0, 200.0),
            _a4_page(),
        )
