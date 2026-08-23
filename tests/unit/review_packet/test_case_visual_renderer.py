from evidence_review.review_packet.render_case_visual import render_case_visual_review
from evidence_review.review_packet.render_summary import (
    render_additional_review,
    render_status_band,
    render_summary,
)


def _reference_anchor(
    reference_type: str,
    citation_id: str,
    *,
    table: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "anchor_id": citation_id,
        "type": reference_type,
        "document_id": "DOC-REF",
        "revision_id": "REV-REF",
        "document_name": "설계기준",
        "page": 12,
        "page_asset_key": "reference-page-1",
        "title": "차량 출입구",
        "quote": "차량 출입구는 기준 위치를 확보해야 한다.",
        "bbox": {
            "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
            "coordinates": [72.0, 420.0, 510.0, 460.0],
        },
        "table": table,
        "visual": (
            {"kind": reference_type.casefold()}
            if reference_type in {"IMAGE", "DIAGRAM", "DRAWING"}
            else None
        ),
    }


def _model() -> dict[str, object]:
    anchors = [
        _reference_anchor("TEXT", "CIT-TEXT"),
        _reference_anchor(
            "TABLE",
            "CIT-TABLE",
            table={
                "cells": [
                    {
                        "row": 0,
                        "column": 0,
                        "text": "구분",
                        "row_span": 1,
                        "column_span": 1,
                        "selected": False,
                    },
                    {
                        "row": 1,
                        "column": 0,
                        "text": "차량 출입구",
                        "row_span": 1,
                        "column_span": 1,
                        "selected": True,
                    },
                ]
            },
        ),
        *[
            _reference_anchor(kind, f"CIT-{kind}")
            for kind in ("PDF_PAGE", "IMAGE", "DIAGRAM", "DRAWING")
        ],
    ]
    return {
        "missing_inputs": [],
        "conflicts": [],
        "exceptions": [],
        "abstention_reasons": [],
        "claims": [
            {
                "claim_id": "CL-I1-1",
                "text": "차량 출입구 위치를 기준과 비교했다.",
                "citation_ids": ["CIT-1"],
                "numeric_tokens": [],
                "citations": [
                    {
                        "citation_id": "CIT-1",
                        "document_name": "설계기준",
                        "title": "차량 출입구",
                        "page_number": 12,
                        "quote": "차량 출입구는 기준 위치를 확보해야 한다.",
                    }
                ],
            }
        ],
        "case_visual_review": {
            "status": "VISUAL_ANALYSIS_VALIDATED",
            "attachment_count": 1,
            "candidate_count": 1,
            "pages": [
                {
                    "asset_key": "ATT-1-p1",
                    "attachment_id": "ATT-1",
                    "document_name": "배치-test.pdf",
                    "source_sha256": "a" * 64,
                    "page": 1,
                    "width": 100.0,
                    "height": 120.0,
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "image_sha256": "b" * 64,
                    "data_uri": "data:image/png;base64,ZmFrZQ==",
                    "candidates": [
                        {
                            "candidate_id": "CAND-1",
                            "source_sha256": "a" * 64,
                            "page": 1,
                            "candidate_type": "VISUAL_OBSERVATION",
                            "origin": "EXTRACTOR",
                            "status": "UNCONFIRMED",
                            "geometry": {
                                "type": "BBOX",
                                "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                                "coordinates": [10.0, 20.0, 80.0, 90.0],
                            },
                            "raw_value": "차량 출입구",
                            "normalized_candidate": None,
                            "extractor": "codex-vision",
                            "extractor_version": "1.0.0",
                            "annotation_id": None,
                            "issue_ids": ["I1"],
                            "issue_questions": ["차량 출입구 기준을 충족하는가"],
                            "claims": [
                                {
                                    "claim_id": "CL-I1-1",
                                    "text": "차량 출입구 위치를 기준과 비교했다.",
                                    "issue_ids": ["I1"],
                                    "citation_ids": ["CIT-1"],
                                }
                            ],
                            "review_statuses": ["NOT_SATISFIED"],
                            "tone": "issue",
                            "display_value": "차량 출입구",
                        }
                    ],
                }
            ],
            "reference_documents": [
                {
                    "document_id": "DOC-REF",
                    "revision_id": "REV-REF",
                    "document_name": "설계기준",
                    "page_count": 30,
                    "page_asset_keys": ["reference-page-1"],
                }
            ],
            "reference_pages": [
                {
                    "asset_key": "reference-page-1",
                    "document_id": "DOC-REF",
                    "revision_id": "REV-REF",
                    "page": 12,
                    "source_hash": "c" * 64,
                    "width": 595.0,
                    "height": 842.0,
                    "origin_x": 0.0,
                    "origin_y": 0.0,
                    "rotation": 0,
                    "box_kind": "MEDIA_BOX",
                    "image_sha256": "d" * 64,
                    "data_uri": "data:image/png;base64,cmVmZXJlbmNl",
                }
            ],
            "findings": [
                {
                    "finding_id": "CAND-1",
                    "reference_anchors": anchors,
                    "subject_region": {
                        "page_asset_key": "ATT-1-p1",
                        "attachment_id": "ATT-1",
                        "page": 1,
                        "geometry": {"coordinate_system": "IMAGE_TOP_LEFT_PIXELS"},
                    },
                }
            ],
        },
    }


def test_renderer_builds_issue_119_reference_subject_findings_workspace() -> None:
    model = _model()
    html = render_case_visual_review(model)

    assert "기준 근거" in html
    assert "사용자 파일" in html
    assert "대조 결과" in html
    assert "설계기준" in html
    assert "차량 출입구는 기준 위치를 확보해야 한다." in html
    assert 'data-reference-page="reference-page-1"' in html
    assert 'data-page-image-source="reference-page-1"' in html
    for reference_type in ("TEXT", "TABLE", "PDF_PAGE", "IMAGE", "DIAGRAM", "DRAWING"):
        assert f'data-reference-type="{reference_type}"' in html
    assert '<mark class="reference-quote-highlight">' in html
    assert 'data-table-cell="1:0"' in html
    assert 'class="reference-table-cell is-target"' in html
    assert 'class="reference-overlay"' in html
    assert '<rect class="reference-anchor-shape"' in html
    assert 'data-reference-prev' in html
    assert 'data-reference-next' in html
    assert 'data-reference-zoom-in' in html
    assert 'data-reference-zoom-out' in html
    assert 'data-reference-fit' in html
    assert 'src="data:image/png;base64,ZmFrZQ=="' in html
    assert 'data-case-overlay="CAND-1"' in html
    assert '<rect class="case-visual-shape" x="10" y="20" width="70" height="70"' in html
    assert 'data-case-divider' in html
    for function_name in (
        "showReferencePage",
        "showSubjectPage",
        "focusStage",
        "fitStage",
        "activateFinding",
    ):
        assert f"function {function_name}" in html
    assert "requestAnimationFrame" in html
    assert "new WeakMap()" in html
    assert "Math.min(5,Math.max(.5" in html
    assert "{passive:false}" in html
    assert "setPointerCapture" in html
    assert "releasePointerCapture" in html
    assert "data-reference-stage" in html
    assert "data-case-stage" in html
    assert "data-reference-transform" in html
    assert "data-case-transform" in html

    assert 'role="separator"' in html
    assert 'data-finding-prev' in html
    assert 'data-finding-next' in html
    assert 'data-case-zoom-in' in html
    assert 'data-case-zoom-out' in html
    assert "마우스 휠로 커서 위치 기준 확대·축소" in html
    assert "http://" not in html
    assert "https://" not in html


def test_renderer_consumes_case_raster_payload_before_review_model_serialization() -> None:
    model = _model()

    html = render_case_visual_review(model)

    assert html.count("data:image/png;base64,ZmFrZQ==") == 1
    assert html.count("data:image/png;base64,cmVmZXJlbmNl") == 1
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    pages = visual["pages"]
    assert isinstance(pages, list)
    assert "data_uri" not in pages[0]
    reference_pages = visual["reference_pages"]
    assert isinstance(reference_pages, list)
    assert "data_uri" not in reference_pages[0]


def test_renderer_shows_explicit_no_reference_state_without_inventing_evidence() -> None:
    model = _model()
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    findings = visual["findings"]
    assert isinstance(findings, list)
    findings[0]["reference_anchors"] = []
    pages = visual["pages"]
    assert isinstance(pages, list)
    pages[0]["candidates"][0]["claims"] = []
    model["claims"] = []

    html = render_case_visual_review(model)

    assert "직접 연결된 기준 근거가 없습니다." in html
    assert "법규·설계기준과 동일 비교대상인지 추가 확인이 필요합니다." in html


def test_visual_workspace_hides_legacy_header_and_summary() -> None:
    model = _model()

    assert render_status_band(model) == ""
    assert render_summary(model) == ""


def test_renderer_returns_empty_for_non_visual_model() -> None:
    assert render_case_visual_review({}) == ""


def test_summary_flow_spans_visual_workspace_across_parent_review_grid() -> None:
    html = render_additional_review(_model())

    assert 'class="visual-review-grid-span"' in html
    assert 'style="grid-column:1/-1;width:100%;min-width:0"' in html
    assert 'id="case-visual-review"' in html
    assert 'id="additional-review"' not in html
    assert "body:has(#case-visual-review){overflow:hidden}" in html
    assert ".review-workspace>:not(.visual-review-grid-span):not(#decision-form)" in html
    assert ".case-visual-transform img{pointer-events:none" in html
    assert "#decision-form:hover" in html


def test_visual_workspace_does_not_duplicate_legacy_additional_review_strip() -> None:
    model = _model()
    model["missing_inputs"] = ["I1: 추가 기준 확인 필요"]

    html = render_additional_review(model)

    assert 'id="case-visual-review"' in html
    assert 'id="additional-review"' not in html
