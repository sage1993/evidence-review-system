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
                                }
                            ],
                            "review_statuses": ["NOT_SATISFIED"],
                            "tone": "issue",
                            "display_value": "차량 출입구",
                        }
                    ],
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
    assert 'src="data:image/png;base64,ZmFrZQ=="' in html
    assert 'data-case-overlay="CAND-1"' in html
    assert '<rect class="case-visual-shape" x="10" y="20" width="70" height="70"' in html
    assert 'data-case-divider' in html
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
    assert ".case-visual-transform img{pointer-events:none" in html
    assert "#decision-form:hover" in html


def test_visual_workspace_does_not_duplicate_legacy_additional_review_strip() -> None:
    model = _model()
    model["missing_inputs"] = ["I1: 추가 기준 확인 필요"]

    html = render_additional_review(model)

    assert 'id="case-visual-review"' in html
    assert 'id="additional-review"' not in html
