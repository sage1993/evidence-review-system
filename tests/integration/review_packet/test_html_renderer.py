import base64
from pathlib import Path

from ansim_review.review_packet.html_renderer import render_review_html


def test_self_contained_html_has_traceability_overlay_and_blank_decision(
    tmp_path: Path,
) -> None:
    images = tmp_path / "pages" / "REV1"
    images.mkdir(parents=True)
    page = images / "page-0003.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    model = {
        "run_id": "RUN-1",
        "status": "READY_FOR_HUMAN_REVIEW",
        "human_decision": None,
        "decision_options": [],
        "question": "<검토 질문>",
        "claims": [
            {
                "claim_id": "C1",
                "text": "<script>alert(1)</script>",
                "numeric_tokens": ["9.375%"],
                "citations": [
                    {
                        "citation_id": "CIT-E1",
                        "document_id": "DOC1",
                        "revision_id": "REV1",
                        "page_number": 3,
                        "evidence_id": "E1",
                        "bbox": [10.0, 20.0, 110.0, 40.0],
                        "source_hash": "a" * 64,
                        "title": "제3조",
                        "quote": "정확한 <인용문>",
                        "evidence_type": "clause",
                    }
                ],
            }
        ],
        "calculations": [
            {
                "calculation_result_id": "CAL1",
                "status": "SUCCESS",
                "formula_id": "RATIO",
                "formula_version": "1",
                "substitution": "30/320",
                "display_result": "9.375%",
                "raw_result": "0.09375",
                "comparison": "BELOW_THRESHOLD",
            }
        ],
        "rules": [
            {
                "rule_id": "RULE1",
                "rule_version": "1",
                "status": "NOT_SATISFIED",
                "reason_codes": [],
            }
        ],
        "confidence": {
            "score": "0.9000",
            "level": "HIGH",
            "factors": [
                {
                    "name": "traceability",
                    "value": "1.0000",
                    "weight": "0.15",
                    "contribution": "0.1500",
                    "source": "evidence",
                }
            ],
        },
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
    }
    html = render_review_html(model, images.parent)
    encoded_page = base64.b64encode(page.read_bytes()).decode()
    assert "DOC1 · page 3" in html
    assert "정확한 &lt;인용문&gt;" in html
    assert 'data-bbox="10.0,20.0,110.0,40.0"' in html
    assert "9.375%" in html
    assert "traceability" in html
    assert "Machine evaluation is not the final decision" in html
    assert "<script>" not in html
    assert "checked" not in html
    assert "data:image/png;base64," + encoded_page in html
    assert "<svg" in html and "<rect" in html
    assert "@page" in html and "size: A4" in html
