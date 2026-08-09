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


def test_renderer_matches_approved_drawing_review_workspace_structure() -> None:
    render_annotation_html = _renderer()

    html = render_annotation_html(_model(), b"\x89PNG\r\n\x1a\nfixture", "image/png")

    assert "도면 근거 검토 화면" in html
    assert 'id="topStatus"' in html
    assert "입력 확인 필요" in html
    assert 'class="metrics"' in html
    assert html.count('class="metric"') == 4
    assert 'class="main-grid"' in html
    assert 'id="featureList"' in html
    assert 'id="drawingStage"' in html
    assert 'id="selectedObject"' in html
    assert 'id="selectedCoords"' in html
    assert 'id="selectedStatus"' in html
    for mode in ("original", "detection", "compare"):
        assert f'data-display-mode="{mode}"' in html
    for tab in ("evidence", "rules", "confirmation"):
        assert f'data-workspace-tab="{tab}"' in html
        assert f'data-workspace-pane="{tab}"' in html
    assert 'id="reviewer-action"' in html
    assert "검토자 확인 기록" in html
    assert "파싱 엔진" in html
    assert "규칙·계산 엔진" in html
    assert 'data-status-strip' in html


def test_annotation_workspace_matches_issue_5_semantic_layout() -> None:
    html = _renderer()(_model(), b"\x89PNG\r\n\x1a\nfixture", "image/png")

    assert 'class="app-shell"' in html
    assert 'class="topbar"' in html
    assert html.count('class="metric"') == 4
    assert 'class="main-grid"' in html
    assert 'class="candidate-panel' in html
    assert 'class="viewer-panel' in html
    assert 'class="detail-panel' in html
    assert "도면 입력 확인" in html
    assert "보류 사유" in html
    assert "연결된 승인 규칙" in html
    assert "검토자 확인 기록" in html
    assert "검토자 최종 판정" not in html


def test_annotation_workspace_uses_bounded_accessible_tabs() -> None:
    html = _renderer()(_model(), b"\x89PNG\r\n\x1a\nfixture", "image/png")

    assert 'data-open-confirmation>확인 기록 열기</button>' in html
    assert 'data-workspace-tab="confirmation">확인 기록 열기</button>' not in html
    assert 'role="tab" id="annotation-tab-evidence"' in html
    assert 'aria-controls="annotation-pane-evidence" aria-selected="true"' in html
    assert 'role="tab" id="annotation-tab-rules"' in html
    assert 'aria-controls="annotation-pane-rules" aria-selected="false"' in html
    assert 'role="tab" id="annotation-tab-confirmation"' in html
    assert 'aria-controls="annotation-pane-confirmation" aria-selected="false"' in html
    assert 'role="tabpanel" id="annotation-pane-evidence"' in html
    assert 'aria-labelledby="annotation-tab-evidence"' in html
    assert 'role="tabpanel" id="annotation-pane-rules"' in html
    assert 'role="tabpanel" id="annotation-pane-confirmation"' in html


def test_renderer_localizes_visible_workspace_copy_without_changing_contract_values() -> None:
    render_annotation_html = _renderer()

    html = render_annotation_html(_model(), b"\x89PNG\r\n\x1a\nfixture", "image/png")

    for localized_copy in (
        "입력 확인 필요",
        "로컬 · 오프라인",
        "검출 근거",
        "검증된 원본",
        "선택 근거",
        "결정론적 실행 경계",
        "추가 전용 인적 조치",
        "해시 검증 완료 · 읽기 전용",
        "인적 최종 결정 · 없음",
        "도로 폭 표기",
        "신규 생성",
    ):
        assert localized_copy in html

    for contract_value in (
        'data-candidate-type="ROAD_WIDTH_TEXT"',
        'data-candidate-type-label="도로 폭 표기"',
        'data-candidate-origin-label="검토자 수동"',
        'data-candidate-status="CREATED"',
        'data-candidate-status-label="신규 생성"',
        'value="POINT"',
        'value="BBOX"',
        'value="LINESTRING"',
        'value="POLYGON"',
    ):
        assert contract_value in html

    for geometry_value, localized_label in (
        ("POINT", "점"),
        ("BBOX", "사각형"),
        ("LINESTRING", "선"),
        ("POLYGON", "다각형"),
    ):
        assert f'<option value="{geometry_value}">{localized_label}</option>' in html

    for english_copy in (
        "INPUT CONFIRMATION REQUIRED",
        "LOCAL · OFFLINE",
        "DETECTED EVIDENCE",
        "VERIFIED SOURCE",
        "SELECTED EVIDENCE",
        "DETERMINISTIC BOUNDARY",
        "Parse Engine",
        "Rule / Math Engine",
        "APPEND-ONLY HUMAN ACTION",
        "HASH VERIFIED · READ ONLY",
        "human_decision: null",
    ):
        assert english_copy not in html


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
