from evidence_review.review_packet.render_case_visual import render_case_visual_review
from evidence_review.review_packet.render_summary import render_additional_review


def _model() -> dict[str, object]:
    return {
        "missing_inputs": [],
        "conflicts": [],
        "exceptions": [],
        "abstention_reasons": [],
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


def test_renderer_shows_actual_case_page_and_svg_overlay() -> None:
    html = render_case_visual_review(_model())

    assert "도면·이미지 확인 위치" in html
    assert 'src="data:image/png;base64,ZmFrZQ=="' in html
    assert 'data-case-overlay="CAND-1"' in html
    assert '<rect x="10" y="20" width="70" height="70"' in html
    assert "차량 출입구" in html
    assert "마우스 휠로 확대·축소" in html
    assert "http://" not in html
    assert "https://" not in html


def test_renderer_returns_empty_for_non_visual_model() -> None:
    assert render_case_visual_review({}) == ""


def test_summary_flow_keeps_visual_section_without_other_additional_review() -> None:
    html = render_additional_review(_model())

    assert 'id="case-visual-review"' in html
    assert 'id="additional-review"' not in html
