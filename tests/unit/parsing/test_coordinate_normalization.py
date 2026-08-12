import pytest

from ansim_review.contracts.common import BBox
from ansim_review.parsing.pdf_geometry import normalize_bbox, project_bbox_for_display


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


def test_pdf_bottom_left_a3_landscape_coordinates_are_preserved() -> None:
    assert normalize_bbox(
        (100.0, 100.0, 1100.0, 700.0),
        "PDF_BOTTOM_LEFT",
        1191.0,
        842.0,
    ) == BBox(100.0, 100.0, 1100.0, 700.0)


def test_bbox_boundary_tolerance_clamps_exactly_half_point() -> None:
    assert normalize_bbox(
        (-0.5, 0.0, 1191.5, 842.0),
        "PDF_BOTTOM_LEFT",
        1191.0,
        842.0,
    ) == BBox(0.0, 0.0, 1191.0, 842.0)

@pytest.mark.parametrize(
    ("rotation", "expected"),
    [
        (0, BBox(100, 200, 200, 300)),
        (90, BBox(400, 100, 500, 200)),
        (180, BBox(300, 400, 400, 500)),
        (270, BBox(200, 300, 300, 400)),
    ],
)
def test_canonical_bbox_projects_to_rotated_display(
    rotation: int,
    expected: BBox,
) -> None:
    assert project_bbox_for_display(
        BBox(100, 200, 200, 300),
        500,
        700,
        rotation=rotation,
    ) == expected