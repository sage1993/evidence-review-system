from __future__ import annotations

import importlib

import pytest

from ansim_review.contracts.drawing import DrawingCandidate, Geometry
from ansim_review.drawing_review.view_model import (
    DrawingPage,
    build_drawing_review_view_model,
)


_SOURCE_HASH = "a" * 64


def _renderer():
    try:
        module = importlib.import_module("ansim_review.drawing_review.html_renderer")
    except ModuleNotFoundError:
        pytest.fail("drawing annotation HTML renderer is not implemented")
    return module.render_annotation_html


def _candidate(
    candidate_id: str,
    geometry: Geometry,
    *,
    candidate_type: str = "ROAD_WIDTH_TEXT",
    raw_value: str | None = None,
) -> DrawingCandidate:
    return DrawingCandidate(
        candidate_id=candidate_id,
        source_sha256=_SOURCE_HASH,
        page=1,
        candidate_type=candidate_type,
        origin="REVIEWER_MANUAL",
        status="CREATED",
        geometry=geometry,
        raw_value=raw_value,
        normalized_candidate=None,
        extractor=None,
        extractor_version=None,
        annotation_id=f"ANN-{candidate_id}",
    )


def _model() -> dict[str, object]:
    page = DrawingPage(
        source_sha256=_SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=400.0,
        height=300.0,
    )
    candidates = (
        _candidate(
            "CAND-POINT",
            Geometry(
                type="POINT",
                coordinate_system="IMAGE_TOP_LEFT_PIXELS",
                coordinates=(20.0, 20.0),
            ),
        ),
        _candidate(
            "CAND-BBOX",
            Geometry(
                type="BBOX",
                coordinate_system="IMAGE_TOP_LEFT_PIXELS",
                coordinates=(30.0, 30.0, 100.0, 100.0),
            ),
        ),
        _candidate(
            "CAND-LINE",
            Geometry(
                type="LINESTRING",
                coordinate_system="IMAGE_TOP_LEFT_PIXELS",
                coordinates=((10.0, 150.0), (100.0, 150.0)),
            ),
        ),
        _candidate(
            "CAND-POLYGON",
            Geometry(
                type="POLYGON",
                coordinate_system="IMAGE_TOP_LEFT_PIXELS",
                coordinates=(
                    (200.0, 200.0),
                    (250.0, 200.0),
                    (250.0, 250.0),
                    (200.0, 200.0),
                ),
            ),
        ),
    )
    return build_drawing_review_view_model(page, candidates)


def test_renderer_projects_all_m0_geometry_types() -> None:
    render_annotation_html = _renderer()

    html = render_annotation_html(_model(), b"\x89PNG\r\n\x1a\nfixture", "image/png")

    assert '<circle data-candidate-id="CAND-POINT"' in html
    assert '<rect data-candidate-id="CAND-BBOX"' in html
    assert '<polyline data-candidate-id="CAND-LINE"' in html
    assert '<polygon data-candidate-id="CAND-POLYGON"' in html


def test_renderer_is_self_contained_and_leaves_actions_unselected() -> None:
    render_annotation_html = _renderer()

    html = render_annotation_html(_model(), b"\x89PNG\r\n\x1a\nfixture", "image/png")

    assert "https://" not in html
    assert "http://" not in html
    assert html.count("data:image/png;base64,") == 1
    assert " checked" not in html
    assert 'name="review-action"' in html


def test_renderer_escapes_candidate_text() -> None:
    render_annotation_html = _renderer()
    page = DrawingPage(
        source_sha256=_SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=400.0,
        height=300.0,
    )
    candidate = _candidate(
        "CAND-ESCAPE",
        Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(10.0, 10.0, 20.0, 20.0),
        ),
        candidate_type="TYPE<&",
        raw_value="<script>alert(1)</script>",
    )
    model = build_drawing_review_view_model(page, (candidate,))

    html = render_annotation_html(model, b"\x89PNG\r\n\x1a\nfixture", "image/png")

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "TYPE&lt;&amp;" in html


def test_renderer_rejects_unsupported_image_mime() -> None:
    render_annotation_html = _renderer()

    with pytest.raises(ValueError, match="image MIME"):
        render_annotation_html(_model(), b"fixture", "image/tiff")
