import re
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.review_packet.render_case_visual import (
    case_visual_css,
    render_case_visual_review,
)
from evidence_review.review_packet.render_case_visual_lazy import (
    render_case_visual_review as render_lazy_case_visual_review,
)
from evidence_review.review_packet.render_summary import (
    render_additional_review,
    render_status_band,
    render_summary,
    visual_shell_css,
)


def _review_script() -> str:
    return (
        Path(__file__).parents[3]
        / "src"
        / "evidence_review"
        / "review_packet"
        / "assets"
        / "review.js"
    ).read_text(encoding="utf-8")


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
    script = _review_script()

    assert "기준 근거" in html
    assert "사용자 파일" in html
    assert "쟁점 탐색" in html
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
    assert 'data-finding-prev' not in html
    assert 'data-finding-next' not in html
    assert 'data-case-zoom-in' in html
    assert 'data-case-zoom-out' in html
    assert 'data-case-overlay-mode="selected"' in html
    assert "focusSubjectFinding" in script
    assert "마우스 휠 Zoom" in html
    assert "http://" not in html
    assert "https://" not in html


def test_case_visual_markup_has_no_inline_controller_or_style() -> None:
    html = render_case_visual_review(_model())

    assert "<script" not in html
    assert "<style" not in html


def test_issue_152_case_visual_exposes_distinct_readable_view_controls() -> None:
    """A future ambiguous reset control must not replace the three view modes."""
    html = render_case_visual_review(_model())
    css = case_visual_css()
    script = _review_script()

    for control, label in (
        ("data-case-fit-screen", "화면 맞춤"),
        ("data-case-fit-width", "폭 맞춤"),
        ("data-case-original-size", "원본 100%"),
    ):
        assert control in html
        assert f'aria-label="{label}"' in html
        assert f'title="{label}"' in html
    affordances = [
        re.search(rf'<button[^>]*{control}[^>]*>(.*?)</button>', html, re.DOTALL).group(1)
        for control in ("data-case-fit-screen", "data-case-fit-width", "data-case-original-size")
    ]
    assert len(set(affordances)) == 3
    assert "function fitScreen(stage)" in script
    assert "function fitWidth(stage)" in script
    assert "function originalSize(stage)" in script
    assert "fitWidth(pages[0]?.querySelector('[data-case-stage]'))" in script
    assert (
        "#case-visual-review .viewer-controls button{width:40px;height:40px;"
        "min-height:0;display:inline-flex;"
        "align-items:center;justify-content:center;padding:0;line-height:0}"
    ) in css
    assert "#case-visual-review .finding-filter{height:32px;min-height:0" in css
    assert ".case-visual-help{margin:0;padding:8px 12px" in css


def test_issue_152_no_direct_reference_uses_subject_workspace_without_empty_pane() -> None:
    """An unavailable direct comparison must not consume half of the drawing workspace."""
    model = _model()
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    finding = visual["findings"][0]
    assert isinstance(finding, dict)
    finding["direct_claim_ids"] = []

    html = render_case_visual_review(model)
    css = case_visual_css()

    assert 'data-reference-available="false"' in html
    assert 'class="reference-unavailable"' in html
    assert 'class="reference-viewer"' not in html
    assert re.search(r'<button[^>]+data-case-divider', html) is None
    assert (
        '#case-visual-review[data-reference-available="false"] '
        ".comparison-workspace{grid-template-columns:minmax(0,1fr)}"
    ) in css


def test_issue_152_full_renderers_share_named_review_shell_regions() -> None:
    """Visual mode must retain the same reviewer landmarks as reference-only mode."""
    drawing_model = _model()
    drawing_model.update(
        {
            "run_id": "RUN-152",
            "status": "READY_FOR_HUMAN_REVIEW",
            "display_status": "READY_FOR_HUMAN_REVIEW",
            "question": "도면 검토 질문",
            "review_items": [],
            "calculations": [],
            "rules": [],
            "summary": {},
            "audit": {},
            "claims": [],
        }
    )
    reference_model = dict(drawing_model)
    reference_model.pop("case_visual_review")

    drawing_html = render_review_html(drawing_model, Path("."))
    reference_html = render_review_html(reference_model, Path("."))

    expected_regions = (
        "status-question",
        "evidence-workspace",
        "detail-issue-results",
        "human-decision",
        "audit",
    )
    for html in (drawing_html, reference_html):
        assert 'data-review-shell="unified"' in html
        assert [
            match.group(1)
            for match in re.finditer(
                r'<section[^>]+data-review-shell-region="([^"]+)"', html
            )
        ] == list(expected_regions)
        assert 'id="review-status"' in html
        assert 'id="review-summary"' in html
        assert 'id="decision-form"' in html
        assert 'id="packet-global-review"' in html


def test_multi_page_renderer_removes_hidden_pages_from_layout_and_pointer_events() -> None:
    model = _model()
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    pages = visual["pages"]
    assert isinstance(pages, list)
    second_page = dict(pages[0])
    second_page["asset_key"] = "ATT-1-p2"
    second_page["page"] = 2
    pages.append(second_page)

    html = render_case_visual_review(model)

    assert ".case-visual-page[hidden]{display:none!important}" in case_visual_css()
    assert 'data-case-page="ATT-1-p2"' in html


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
    assert 'data-case-decision-open' not in html


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


def test_reference_stage_keeps_anchor_content_outside_independent_transform() -> None:
    html = render_case_visual_review(_typed_reference_model())

    article_start = html.index('<article class="reference-viewer-item"')
    article_end = html.index("</article>", article_start)
    article = html[article_start:article_end]
    transform_start = article.index('<div class="reference-page-transform"')

    assert 'data-reference-stage' in article
    assert 'tabindex="0"' in article
    assert 'data-reference-transform' in article
    assert article.index("<blockquote>") < transform_start
    assert transform_start < article.index('class="reference-raster-layer"')
    assert transform_start < article.index('class="reference-overlay-layer"')


def test_renderer_exposes_independent_subject_and_reference_focus_contract() -> None:
    html = render_case_visual_review(_typed_reference_model())
    script = _review_script()

    assert "function focusSubjectFinding" in script
    assert "function focusReferenceFinding" in script
    assert "referenceStates" in script
    assert "function preferredReferenceItem" in script
    assert 'data-reference-role="direct"' in html
    assert 'data-reference-role="related"' in html


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
    assert "직접 기준 근거가 없어 기준 비교 창을 숨겼습니다." in html
    assert "직접 대조 가능한 기준을 찾지 못했습니다." in html
    assert "관련 근거 1건" in html
    assert "직접 인용문" in html
    assert 'data-reference-role="related"' in html
    assert 'class="reference-viewer"' not in html
    assert re.search(r'<button[^>]+data-case-divider', html) is None


def test_renderer_consumes_case_raster_payload_before_review_model_serialization() -> None:
    model = _model()

    html = render_case_visual_review(model)

    assert html.count("data:image/png;base64,ZmFrZQ==") == 1
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    pages = visual["pages"]
    assert isinstance(pages, list)
    assert "data_uri" not in pages[0]


def test_issue_152_visual_workspace_keeps_shared_status_and_question_regions() -> None:
    model = _model()

    assert 'id="review-status"' in render_status_band(model)
    assert 'id="review-summary"' in render_summary(model)


def test_renderer_returns_empty_for_non_visual_model() -> None:
    assert render_case_visual_review({}) == ""


def test_visual_fragment_leaves_styles_in_the_document_shell() -> None:
    html = render_case_visual_review(_model())

    assert "<style>" not in html
    assert "<script" not in html


def test_summary_flow_spans_visual_workspace_across_parent_review_grid() -> None:
    html = render_additional_review(_model())
    css = case_visual_css() + visual_shell_css()

    assert 'class="visual-review-grid-span"' in html
    assert 'style="grid-column:1/-1;width:100%;min-width:0"' not in html
    assert 'id="case-visual-review"' in html
    assert 'id="additional-review"' not in html
    assert "body:has(#case-visual-review){overflow:hidden}" in css
    assert ".review-workspace>:not(.visual-review-grid-span):not(#decision-form)" in css
    assert 'body[data-visual-decision-open="true"]' not in css
    assert "#decision-form:hover" not in css
    assert "#decision-form:focus-within" not in css
    assert "pointer-events:none!important" not in css
    assert 'data-case-decision-open' not in html
    assert 'data-case-decision-backdrop' not in html
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


def test_lazy_renderer_binds_reference_page_identity_without_eager_href() -> None:
    model = _typed_reference_model()
    html = render_lazy_case_visual_review(model)

    assert 'data-reference-page-image' in html
    assert (
        'data-reference-page-src="./page-images/REV-REF/12/'
        + "c" * 64
        + '"'
    ) in html
    assert (
        re.search(
            r'<image[^>]+data-reference-page-image[^>]+href="[^"]+"',
            html,
        )
        is None
    )
    urls = set(re.findall(r'data-reference-page-src="([^"]+)"', html))
    assert urls == {"./page-images/REV-REF/12/" + "c" * 64}
    assert 'data-case-page-src="./case-pages/' in html
    assert 'data-reference-page-src="./page-images/' in html


def test_reference_pages_remain_metadata_only_in_visual_model() -> None:
    model = _typed_reference_model()
    render_lazy_case_visual_review(model)

    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    reference_pages = visual["reference_pages"]
    assert isinstance(reference_pages, list)
    assert all("data_uri" not in page for page in reference_pages)
    assert all("image_bytes" not in page for page in reference_pages)
    assert all("image_path" not in page for page in reference_pages)
