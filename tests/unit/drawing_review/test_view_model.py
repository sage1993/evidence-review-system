from __future__ import annotations

import importlib

import pytest

from evidence_review.contracts.drawing import DrawingCandidate, Geometry

_SOURCE_HASH = "a" * 64


def _api():
    try:
        module = importlib.import_module("evidence_review.drawing_review.view_model")
    except ModuleNotFoundError:
        pytest.fail("drawing review view-model module is not implemented")
    return module.DrawingPage, module.build_drawing_review_view_model


def _candidate(
    candidate_id: str,
    *,
    source_sha256: str = _SOURCE_HASH,
    page: int = 1,
    coordinate_system: str = "IMAGE_TOP_LEFT_PIXELS",
    geometry_type: str = "BBOX",
    coordinates: object = (10.0, 20.0, 30.0, 40.0),
) -> DrawingCandidate:
    return DrawingCandidate(
        candidate_id=candidate_id,
        source_sha256=source_sha256,
        page=page,
        candidate_type="ROAD_WIDTH_TEXT",
        origin="REVIEWER_MANUAL",
        status="CREATED",
        geometry=Geometry(
            type=geometry_type,  # type: ignore[arg-type]
            coordinate_system=coordinate_system,  # type: ignore[arg-type]
            coordinates=coordinates,  # type: ignore[arg-type]
        ),
        raw_value=None,
        normalized_candidate="8.0 m",
        extractor=None,
        extractor_version=None,
        annotation_id=f"ANN-{candidate_id}",
    )


def test_build_view_model_sorts_candidates_by_stable_id() -> None:
    DrawingPage, build_drawing_review_view_model = _api()
    page = DrawingPage(
        source_sha256=_SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )

    model = build_drawing_review_view_model(
        page,
        (_candidate("CAND-B"), _candidate("CAND-A")),
    )

    assert model["format"] == "evidence-review/drawing-review-view"
    assert model["version"] == 1
    assert [item["candidate_id"] for item in model["candidates"]] == [
        "CAND-A",
        "CAND-B",
    ]
    assert model["candidates"][0]["geometry"] == {
        "type": "BBOX",
        "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
        "coordinates": [10.0, 20.0, 30.0, 40.0],
    }


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (_candidate("CAND-SOURCE", source_sha256="b" * 64), "source_sha256"),
        (_candidate("CAND-PAGE", page=2), "page"),
        (
            _candidate(
                "CAND-COORDINATE",
                coordinate_system="PDF_BOTTOM_LEFT_POINTS",
            ),
            "coordinate_system",
        ),
    ],
)
def test_build_view_model_rejects_candidate_authority_mismatch(
    candidate: DrawingCandidate,
    message: str,
) -> None:
    DrawingPage, build_drawing_review_view_model = _api()
    page = DrawingPage(
        source_sha256=_SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )

    with pytest.raises(ValueError, match=message):
        build_drawing_review_view_model(page, (candidate,))


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate("CAND-POINT", geometry_type="POINT", coordinates=(1001.0, 20.0)),
        _candidate(
            "CAND-BBOX-OUTSIDE",
            geometry_type="BBOX",
            coordinates=(10.0, 20.0, 1001.0, 40.0),
        ),
        _candidate(
            "CAND-LINE-OUTSIDE",
            geometry_type="LINESTRING",
            coordinates=((10.0, 20.0), (30.0, 801.0)),
        ),
        _candidate(
            "CAND-POLYGON-OUTSIDE",
            geometry_type="POLYGON",
            coordinates=(
                (10.0, 20.0),
                (30.0, 20.0),
                (30.0, 801.0),
                (10.0, 20.0),
            ),
        ),
    ],
)
def test_build_view_model_rejects_geometry_outside_page(
    candidate: DrawingCandidate,
) -> None:
    DrawingPage, build_drawing_review_view_model = _api()
    page = DrawingPage(
        source_sha256=_SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )

    with pytest.raises(ValueError, match="page bounds"):
        build_drawing_review_view_model(page, (candidate,))
