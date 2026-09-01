import re

from evidence_review.review_packet.render_case_visual import render_case_visual_review
from evidence_review.review_packet.render_summary import (
    render_additional_review,
    render_status_band,
    render_summary,
)


def _model() -> dict[str, object]:
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
                                    "relation": "direct",
                                }
                            ],
                            "review_statuses": ["NOT_SATISFIED"],
                            "tone": "issue",
                            "display_value": "차량 출입구",
                        }
                    ],
                }
            ],
            "findings": [
                {
                    "finding_id": "VF-1",
                    "title": "차량 출입구",
                    "category": "visual_observation",
                    "status": "mismatch",
                    "page_asset_key": "ATT-1-p1",
                    "candidate_ids": ["CAND-1"],
                    "issue_ids": ["I1"],
                    "subject_value": "차량 출입구",
                    "focus_bbox": [10.0, 20.0, 80.0, 90.0],
                    "direct_claim_ids": ["CL-I1-1"],
                    "related_claim_ids": [],
                }
            ],
        },
    }


def _reference_anchor(
    anchor_id: str,
    reference_type: str,
    role: str = "direct",
    *,
    table: dict[str, object] | None = None,
    selected_visual: bool = False,
) -> dict[str, object]:
    return {
        "anchor_id": anchor_id,
        "type": reference_type,
        "reference_role": role,
        "document_id": "DOC-REF",
        "revision_id": "REV-REF",
        "document_name": "설계기준",
        "page": 12,
        "page_asset_key": "reference-page-1",
        "title": f"{reference_type} 기준",
        "quote": "직접 인용문" if reference_type != "PDF_PAGE" else None,
        "bbox": {
            "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
            "coordinates": [10.0, 20.0, 100.0, 40.0],
        },
        "table": table,
        "visual": {"kind": "verified-reference"} if selected_visual else None,
    }


def _typed_reference_model() -> dict[str, object]:
    model = _model()
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    visual["reference_pages"] = [
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
        }
    ]
    table = {
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
                "text": "3.0m 이상",
                "row_span": 1,
                "column_span": 1,
                "selected": True,
            },
        ]
    }
    typed_anchors = [
        _reference_anchor("CIT-TEXT", "TEXT"),
        _reference_anchor("CIT-TABLE", "TABLE", table=table),
        _reference_anchor("CIT-PAGE", "PDF_PAGE"),
        _reference_anchor("CIT-IMAGE", "IMAGE", selected_visual=True),
        _reference_anchor("CIT-DIAGRAM", "DIAGRAM", selected_visual=True),
        _reference_anchor("CIT-DRAWING", "DRAWING", "related", selected_visual=True),
    ]
    finding = visual["findings"][0]
    assert isinstance(finding, dict)
    finding["direct_reference_anchors"] = typed_anchors[:5]
    finding["related_reference_anchors"] = typed_anchors[5:]
    return model


def test_renderer_builds_issue_119_reference_subject_findings_workspace() -> None:
    model = _model()
    html = render_case_visual_review(model)

    assert "기준 근거" in html
    assert "사용자 파일" in html
    assert "대조 결과" in html
    assert "설계기준" in html
    assert "차량 출입구는 기준 위치를 확보해야 한다." in html
    assert 'data-case-page-src="data:image/png;base64,ZmFrZQ=="' in html
    assert (
        re.search(
            r'(?<![\w-])src\s*=\s*"data:image/png;base64,ZmFrZQ=="',
            html,
        )
        is None
    )
    assert 'data-case-overlay="CAND-1"' in html
    assert '<rect class="case-visual-geometry" fill="none"' in html
    assert 'data-case-divider' in html
    assert 'role="separator"' in html
    assert 'data-finding-prev' in html
    assert 'data-finding-next' in html
    assert 'data-case-zoom-in' in html
    assert 'data-case-zoom-out' in html
    assert 'data-case-overlay-mode="selected"' in html
    assert "focusSubjectFinding" in html
    assert "마우스 휠 Zoom" in html
    assert "http://" not in html
    assert "https://" not in html


def test_renderer_exposes_all_six_reference_types() -> None:
    html = render_case_visual_review(_typed_reference_model())

    assert 'data-reference-type="TEXT"' in html
    assert 'data-reference-type="TABLE"' in html
    assert 'data-reference-type="PDF_PAGE"' in html
    assert 'data-reference-type="IMAGE"' in html
    assert 'data-reference-type="DIAGRAM"' in html
    assert 'data-reference-type="DRAWING"' in html
    assert 'data-reference-page="reference-page-1"' in html
    assert 'data-reference-role="direct"' in html
    assert 'data-reference-role="related"' in html

    assert 'data-case-page=' in html
    assert 'data-case-finding=' in html
    assert 'data-case-page-key=' in html
    assert 'data-case-focus-bbox=' in html
    assert 'data-case-divider' in html
    assert 'data-case-overlay-mode="selected"' in html
    assert 'data-case-decision-open' in html


def test_renderer_marks_only_selected_reference_table_cells_as_targets() -> None:
    html = render_case_visual_review(_typed_reference_model())

    assert 'data-table-cell="0:0"' in html
    assert 'data-table-cell="1:0"' in html
    assert 'class="reference-table-cell is-target"' in html
    assert "3.0m 이상" in html

    table_start = html.index('data-reference-type="TABLE"')
    table_end = html.index("</article>", table_start)
    table_fragment = html[table_start:table_end]
    assert 'class="reference-table-cell"' in table_fragment
    assert 'data-table-cell="0:0"' in table_fragment
    assert 'data-table-cell="1:0"' in table_fragment
    assert 'class="reference-table-cell is-target"' in table_fragment


def test_renderer_does_not_mark_unselected_reference_table_as_target() -> None:
    model = _typed_reference_model()
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    finding = visual["findings"][0]
    assert isinstance(finding, dict)
    direct_anchors = finding["direct_reference_anchors"]
    assert isinstance(direct_anchors, list)
    table_anchor = direct_anchors[1]
    assert isinstance(table_anchor, dict)
    table = table_anchor["table"]
    assert isinstance(table, dict)
    cells = table["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        assert isinstance(cell, dict)
        cell["selected"] = False

    html = render_case_visual_review(model)
    table_start = html.index('data-reference-type="TABLE"')
    table_end = html.index("</article>", table_start)
    table_fragment = html[table_start:table_end]
    assert "is-target" not in table_fragment


def test_renderer_projects_reference_pdf_bottom_left_bbox_to_svg_top_left() -> None:
    html = render_case_visual_review(_typed_reference_model())

    assert 'data-reference-anchor="CIT-TEXT"' in html
    assert 'class="reference-anchor-box"' in html
    assert 'x="10" y="802" width="90" height="20"' in html


def test_related_only_finding_keeps_not_comparable_status() -> None:
    model = _typed_reference_model()
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    finding = visual["findings"][0]
    assert isinstance(finding, dict)
    finding["status"] = "not_comparable"
    finding["direct_claim_ids"] = []
    finding["related_claim_ids"] = ["CL-I1-1"]
    finding["direct_reference_anchors"] = []

    html = render_case_visual_review(model)

    assert 'data-finding-status="not_comparable"' in html
    assert "비교 불가" in html


def test_renderer_consumes_case_raster_payload_before_review_model_serialization() -> None:
    model = _model()

    html = render_case_visual_review(model)

    assert html.count("data:image/png;base64,ZmFrZQ==") == 1
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    pages = visual["pages"]
    assert isinstance(pages, list)
    assert "data_uri" not in pages[0]


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
    assert 'body[data-visual-decision-open="true"]' in html
    assert "#decision-form:hover" in html
    assert "#decision-form:focus-within" in html
    assert "pointer-events:none!important" in html
    assert 'data-case-decision-open' in html
    assert 'data-case-decision-backdrop' in html
    assert "e.key==='Escape'" in html
    assert "data:image/png;base64,ZmFrZQ==" not in html
    assert (
        'data-case-page-src="./case-pages/ATT-1/1/' + "b" * 64 + '"'
        in html
    )


def test_visual_workspace_does_not_duplicate_legacy_additional_review_strip() -> None:
    model = _model()
    model["missing_inputs"] = ["I1: 추가 기준 확인 필요"]

    html = render_additional_review(model)

    assert 'id="case-visual-review"' in html
    assert 'id="additional-review"' not in html
