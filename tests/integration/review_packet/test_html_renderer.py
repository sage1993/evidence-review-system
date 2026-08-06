import base64
import hashlib
import json
from pathlib import Path

import pytest

from ansim_review.review_packet.html_renderer import render_review_html


def _model() -> dict[str, object]:
    return {
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


def _write_page_assets(root: Path) -> bytes:
    images = root / "REV1"
    images.mkdir(parents=True)
    page = images / "page-0003.png"
    page_bytes = b"\x89PNG\r\n\x1a\nverified-fixture"
    page.write_bytes(page_bytes)
    metadata = {
        "format": "ansim/page-image",
        "version": 1,
        "revision_id": "REV1",
        "page_number": 3,
        "source_hash": "a" * 64,
        "pdf_width": 120.0,
        "pdf_height": 200.0,
        "image_sha256": hashlib.sha256(page_bytes).hexdigest(),
    }
    (images / "page-0003.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    return page_bytes


def test_self_contained_html_has_traceability_overlay_and_blank_decision(
    tmp_path: Path,
) -> None:
    page_bytes = _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    encoded_page = base64.b64encode(page_bytes).decode()
    assert "DOC1 · page 3" in html
    assert "정확한 &lt;인용문&gt;" in html
    assert 'data-bbox="10.0,20.0,110.0,40.0"' in html
    assert "9.375%" in html
    assert "traceability" in html
    assert "Machine evaluation is not the final decision" in html
    assert "<script>alert(1)</script>" not in html
    assert "checked" not in html
    assert "data:image/png;base64," + encoded_page in html
    assert '<svg viewBox="0 0 120.0 200.0"' in html
    assert '<rect x="10.0" y="160.0" width="100.0" height="20.0">' in html
    assert "@page" in html and "size: A4" in html


def test_review_workspace_embeds_shared_page_once_and_keeps_provenance(
    tmp_path: Path,
) -> None:
    page_bytes = _write_page_assets(tmp_path / "pages")
    model = _model()
    claims = model["claims"]
    assert isinstance(claims, list)
    first_claim = claims[0]
    assert isinstance(first_claim, dict)
    second_claim = dict(first_claim)
    second_claim["claim_id"] = "C2"
    second_claim["text"] = "Second claim"
    second_claim["citations"] = [
        {
            **first_claim["citations"][0],
            "citation_id": "CIT-E2",
            "evidence_id": "E2",
            "quote": "Second quote",
        }
    ]
    model["claims"] = [first_claim, second_claim]
    model["review_items"] = [
        {
            "item_id": "ITEM-C1",
            "claim_id": "C1",
            "status": "NOT_SATISFIED",
            "completeness": "COMPLETE",
        },
        {
            "item_id": "ITEM-C2",
            "claim_id": "C2",
            "status": "INDETERMINATE",
            "completeness": "INCOMPLETE",
        },
    ]

    html = render_review_html(model, tmp_path / "pages")

    assert 'id="review-summary"' in html
    assert 'id="review-items"' in html
    assert 'id="evidence-viewer"' in html
    assert 'id="detail-tabs"' in html
    assert 'id="decision-form"' in html
    assert html.count("data:image/png;base64,") == 1
    assert "Math." not in html
    assert base64.b64encode(page_bytes).decode() in html
    assert 'data-item-id="ITEM-C1"' in html
    assert 'data-item-id="ITEM-C2"' in html
    assert 'data-asset-key="page-1"' in html
    assert '<div class="page-canvas">' in html
    assert "CIT-E1" in html and "CIT-E2" in html
    assert "REV1" in html
    assert "source SHA-256" in html


def test_review_html_refuses_missing_page_assets(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="verified page image"):
        render_review_html(_model(), tmp_path / "pages")


def test_review_html_rejects_tampered_page_image(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    page = tmp_path / "pages" / "REV1" / "page-0003.png"
    page.write_bytes(page.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="page image hash mismatch"):
        render_review_html(_model(), tmp_path / "pages")
