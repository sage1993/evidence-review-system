from __future__ import annotations

from importlib.resources import files

from ansim_review.contracts.drawing import DrawingCandidate, Geometry
from ansim_review.drawing_review.html_renderer import render_annotation_html
from ansim_review.drawing_review.view_model import (
    DrawingPage,
    build_drawing_review_view_model,
)

SOURCE_HASH = "a" * 64


def _html() -> str:
    page = DrawingPage(
        source_sha256=SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )
    candidate = DrawingCandidate(
        candidate_id="CAND-001",
        source_sha256=SOURCE_HASH,
        page=1,
        candidate_type="DIMENSION_TEXT",
        origin="EXTRACTOR",
        status="UNCONFIRMED",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(100.0, 120.0, 300.0, 180.0),
        ),
        raw_value="8M",
        normalized_candidate="8 m",
        extractor="fixture",
        extractor_version="1",
        annotation_id=None,
    )
    model = build_drawing_review_view_model(page, (candidate,))
    return render_annotation_html(model, b"png-fixture", "image/png")


def _javascript() -> str:
    return (
        files("ansim_review.drawing_review")
        .joinpath("assets", "annotation.js")
        .read_text(encoding="utf-8")
    )


def test_html_exposes_four_geometry_tools_and_action_form() -> None:
    html = _html()

    for geometry_type in ("POINT", "BBOX", "LINESTRING", "POLYGON"):
        assert f'value="{geometry_type}"' in html
    for action in ("ACCEPTED", "REJECTED", "EDITED", "CREATED"):
        assert f'value="{action}"' in html
    assert "data-reviewer" in html
    assert "data-confirmed-value" in html
    assert "data-unit" in html
    assert "data-annotation-id" in html
    assert "data-candidate-type-input" in html
    assert "data-submit-action" in html
    assert "data-action-status" in html
    assert " checked" not in html


def test_svg_exposes_only_coordinate_projection_metadata() -> None:
    html = _html()

    assert 'data-coordinate-system="IMAGE_TOP_LEFT_PIXELS"' in html
    assert 'data-page-height="800.0"' in html
    assert 'data-page-width="1000.0"' in html
    assert "data-source-sha256" not in html


def test_javascript_generates_exact_existing_and_manual_actions() -> None:
    javascript = _javascript()

    assert "function existingActionPayload" in javascript
    assert "function manualCreatePayload" in javascript
    assert 'action: "CREATED"' in javascript
    assert "candidate_id: selectedCandidateId" in javascript
    assert "annotation_id: annotationId.value" in javascript
    assert "candidate_type: candidateTypeInput.value" in javascript
    assert 'fetch(window.location.pathname + "/actions"' in javascript
    assert "JSON.stringify(payload)" in javascript

    for server_owned_field in (
        "source_sha256",
        "confirmation_id",
        "reviewer_token",
        "output_path",
        "relative_path",
    ):
        assert server_owned_field not in javascript


def test_javascript_captures_all_geometry_types_without_domain_calculation() -> None:
    javascript = _javascript()

    for geometry_type in ("POINT", "BBOX", "LINESTRING", "POLYGON"):
        assert f'"{geometry_type}"' in javascript
    assert "createSVGPoint" in javascript
    assert "getScreenCTM" in javascript
    assert "pageHeight - point.y" in javascript

    for forbidden in (
        "Math.round",
        ".toFixed(",
        "scaleFactor",
        "realLength",
        "calculateArea",
        "calculateDistance",
        "thresholdComparison",
        "ruleEvaluation",
        "confidenceScore",
        "localStorage",
        "sessionStorage",
        "eval(",
        "innerHTML",
    ):
        assert forbidden not in javascript


def test_javascript_keeps_actions_unselected_until_reviewer_input() -> None:
    javascript = _javascript()

    assert 'querySelector("input[name=review-action]:checked")' in javascript
    assert "if (!selectedAction)" in javascript
    assert "selectCandidate(button.dataset.candidateId" in javascript
    assert ".checked = true" not in javascript
