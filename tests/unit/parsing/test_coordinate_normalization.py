import pytest

from ansim_review.contracts.common import BBox
from ansim_review.parsing.pdf_geometry import normalize_bbox


def test_top_left_coordinates_become_pdf_bottom_left() -> None:
    assert normalize_bbox((10, 20, 110, 70), "TOP_LEFT", 600, 800) == BBox(
        10.0, 730.0, 110.0, 780.0
    )


def test_rotated_top_left_coordinates_are_unrotated() -> None:
    assert normalize_bbox(
        (500, 400, 600, 500),
        "TOP_LEFT",
        600,
        800,
        rotation=90,
    ) == BBox(100.0, 200.0, 200.0, 300.0)


def test_bbox_outside_tolerance_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside page bounds"):
        normalize_bbox((-1, 20, 110, 70), "TOP_LEFT", 600, 800)
