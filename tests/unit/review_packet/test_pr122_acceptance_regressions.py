from evidence_review.review_packet.render_summary import (
    render_additional_review,
    visual_shell_css,
)
from evidence_review.review_packet.visual_findings import build_semantic_visual_findings


def _candidate(candidate_id: str, value: str) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": "DIMENSION",
        "display_value": value,
        "issue_ids": ["I1"],
        "issue_questions": ["이격거리가 3m 이상 확보되어 있는가?"],
        "claims": [],
        "review_statuses": [],
        "geometry": {
            "type": "BBOX",
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
            "coordinates": [10.0, 10.0, 20.0, 20.0],
        },
    }


def _visual_model() -> dict[str, object]:
    return {
        "status": "ABSTAIN",
        "display_status": "ABSTAIN",
        "abstention_reasons": [],
        "claims": [],
        "case_visual_review": {
            "status": "VISUAL_ANALYSIS_VALIDATED",
            "attachment_count": 1,
            "candidate_count": 0,
            "pages": [
                {
                    "asset_key": "ATT-1-p1",
                    "attachment_id": "ATT-1",
                    "document_name": "drawing.pdf",
                    "source_sha256": "a" * 64,
                    "page": 1,
                    "width": 100.0,
                    "height": 100.0,
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "image_sha256": "b" * 64,
                    "data_uri": "data:image/png;base64,ZmFrZQ==",
                    "candidates": [],
                }
            ],
            "findings": [],
        },
    }


def test_semantic_finding_drops_question_plan_text_from_subject_value() -> None:
    findings = build_semantic_visual_findings(
        [
            {
                "asset_key": "ATT-1-p1",
                "candidates": [
                    _candidate("C1", "이격거리가 3m 이상 확보되어 있는가?"),
                    _candidate("C2", "2.4m"),
                ],
            }
        ]
    )

    assert len(findings) == 1
    assert findings[0]["candidate_ids"] == ["C1", "C2"]
    assert findings[0]["subject_value"] == "2.4m"


def test_visual_decision_uses_the_shared_document_flow() -> None:
    css = visual_shell_css()

    assert "#decision-form:hover" not in css
    assert "#decision-form:focus-within" not in css
    assert "pointer-events:none!important" not in css
    assert 'body[data-visual-decision-open="true"]' not in css


def test_visual_workspace_html_does_not_embed_case_raster_bytes() -> None:
    html = render_additional_review(_visual_model())

    assert "data:image/png;base64,ZmFrZQ==" not in html
    assert (
        'data-case-page-src="./case-pages/ATT-1/1/' + "b" * 64 + '"'
        in html
    )
