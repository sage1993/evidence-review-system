import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from ansim_review.review_packet.html_renderer import render_review_html


def _model() -> dict[str, object]:
    return {
        "run_id": "RUN-1",
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "decision": {
            "allowed_values": [
                "SATISFIED",
                "NOT_SATISFIED",
                "CONDITIONAL",
                "ADDITIONAL_REVIEW_REQUIRED",
            ],
            "human_decision": None,
            "packet_sha256": "b" * 64,
        },
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
                        "page_width": 120.0,
                        "page_height": 200.0,
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
                "rule_result_id": "RR1",
                "rule_id": "RULE1",
                "rule_version": "1",
                "status": "NOT_SATISFIED",
                "missing_inputs": [],
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
        "metadata": {"run_id": "RUN-1", "packet_sha256": "b" * 64},
        "summary": {
            "citation_count": 1,
            "approved_rule_count": 1,
            "calculation_count": 1,
            "missing_input_count": 0,
            "exception_count": 0,
            "conflict_count": 0,
            "confidence_score": "0.9000",
            "confidence_level": "HIGH",
        },
        "audit": {
            "track_a_status": "COMPLETE",
            "track_b_status": "ACCEPT",
            "uncited_count": 0,
            "confidence_factors": [
                {"name": "traceability", "value": "1.0000", "weight": "0.15"}
            ],
            "exceptions": [],
            "conflicts": [],
            "abstention_reasons": [],
        },
        "review_items": [
            {
                "item_id": "ITEM-C1",
                "claim_id": "C1",
                "status": "NOT_SATISFIED",
                "completeness": "COMPLETE",
                "citation_ids": ["CIT-E1"],
                "calculation_ids": ["CAL1"],
                "rule_ids": ["RULE1"],
            }
        ],
    }


def _write_page_assets(
    root: Path,
    *,
    pdf_width: float = 120.0,
    pdf_height: float = 200.0,
) -> bytes:
    images = root / "REV1"
    images.mkdir(parents=True)
    page = images / "page-0003.png"
    page_bytes = b"\x89PNG\r\n\x1a\nverified-fixture"
    page.write_bytes(page_bytes)
    (images / "page-0003.json").write_text(
        json.dumps(
            {
                "format": "ansim/page-image",
                "version": 1,
                "revision_id": "REV1",
                "page_number": 3,
                "source_hash": "a" * 64,
                "pdf_width": pdf_width,
                "pdf_height": pdf_height,
                "image_sha256": hashlib.sha256(page_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return page_bytes


def _decision_form_html(html: str) -> str:
    match = re.search(r'<section id="decision-form".*?</section>', html, re.DOTALL)
    assert match is not None
    return match.group(0)


def _packet_global_review_html(html: str) -> str:
    match = re.search(r'<details id="packet-global-review".*?</details>', html, re.DOTALL)
    assert match is not None
    return match.group(0)


def _complete_domain_model() -> dict[str, object]:
    model = _model()
    model["exceptions"] = ["MISSING_REQUIRED_INPUT"]
    model["conflicts"] = ["SOURCE_CONFLICT"]
    model["abstention_reasons"] = ["TRACK_B_REJECTED"]
    rules = model["rules"]
    summary = model["summary"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    assert isinstance(summary, dict)
    rules[0]["missing_inputs"] = ["site_area"]
    summary.update(
        {"missing_input_count": 1, "exception_count": 1, "conflict_count": 1}
    )
    return model


def _populated_global_audit_model() -> dict[str, object]:
    model = _complete_domain_model()
    audit = model["audit"]
    confidence = model["confidence"]
    assert isinstance(audit, dict) and isinstance(confidence, dict)
    audit["records"] = [
        {"audit_id": "AUDIT1", "status": "TRACE_VERIFIED"},
        {"audit_id": "AUDIT2", "status": "RULE_VERIFIED"},
    ]
    confidence["factors"] = [
        {
            "name": "traceability",
            "value": "1.0000",
            "weight": "0.15",
            "source": "test-fixture-evidence",
        },
        {
            "name": "rule_coverage",
            "value": "0.7500",
            "weight": "0.20",
            "source": "test-fixture-rule-results",
        },
    ]
    return model


def test_default_workspace_is_nondeveloper_first_and_traceable(tmp_path: Path) -> None:
    page_bytes = _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    for text in (
        "검토 준비 완료",
        "1. 검토 결과",
        "2. 판단 근거",
        "질문 &lt;검토 질문&gt;",
        "정확한 &lt;인용문&gt;",
        "인용 좌표",
        "원문 위치 보기",
    ):
        assert text in html
    assert 'data-bbox="10.0,20.0,110.0,40.0"' in html
    assert "<script>alert(1)</script>" not in html
    assert "data:image/png;base64," + base64.b64encode(page_bytes).decode() in html
    assert '<svg viewBox="0 0 120.0 200.0"' in html
    assert '<rect x="10.0" y="160.0" width="100.0" height="20.0">' in html
    assert "checked" not in html


def test_single_claim_and_empty_conditions_do_not_create_empty_sections(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    model["rules"] = []
    model["calculations"] = []
    html = render_review_html(model, tmp_path / "pages")

    assert 'id="review-items"' not in html
    assert 'id="additional-review"' not in html
    assert 'data-detail-tab="rules-calculations"' not in html
    assert "규칙·계산" not in html


def test_multiple_claims_use_generic_navigation_labels(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    claims = model["claims"]
    assert isinstance(claims, list) and isinstance(claims[0], dict)
    model["claims"] = [claims[0], {**claims[0], "claim_id": "C2", "text": "두 번째 주장"}]
    model["review_items"] = [
        {"item_id": "ITEM-C1", "claim_id": "C1", "status": "SATISFIED"},
        {"item_id": "ITEM-C2", "claim_id": "C2", "status": "INDETERMINATE"},
    ]
    html = render_review_html(model, tmp_path / "pages")
    nav = re.search(r'<nav id="review-items".*?</nav>', html, re.DOTALL)

    assert nav is not None
    assert "검토 항목 1" in nav.group(0) and "검토 항목 2" in nav.group(0)
    assert ">C1<" not in nav.group(0) and ">ITEM-C1<" not in nav.group(0)


def test_additional_review_renders_only_present_missing_and_conflict_items(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_complete_domain_model(), tmp_path / "pages")

    assert 'id="additional-review"' in html
    assert "site area" in html
    assert "필요한 입력 자료가 없습니다." in html
    assert "서로 다른 출처의 내용이 일치하지 않습니다." in html
    assert "교차 검증에서 추가 확인이 필요하다고 판단했습니다." in html


def test_internal_ids_hashes_and_confidence_weights_are_collapsed(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_populated_global_audit_model(), tmp_path / "pages")
    audit = _packet_global_review_html(html)
    citation = re.search(r'<article class="citation".*?</article>', html, re.DOTALL)

    assert audit.startswith('<details id="packet-global-review"')
    for value in ("RUN-1", "traceability", "rule_coverage", "0.15", "AUDIT1"):
        assert value in audit
    assert citation is not None
    detail = re.search(r'<details class="citation-audit">.*?</details>', citation.group(0), re.DOTALL)
    assert detail is not None
    for value in ("CIT-E1", "E1", "REV1", "a" * 64):
        assert value in detail.group(0)
    visible = citation.group(0).replace(detail.group(0), "")
    visible_text = re.sub(r"<[^>]+>", "", visible)
    assert "CIT-E1" not in visible_text
    assert "REV1" not in visible_text
    assert "a" * 64 not in visible_text


def test_geometry_missing_and_tampered_page_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="verified page image"):
        render_review_html(_model(), tmp_path / "missing")

    _write_page_assets(tmp_path / "mismatch", pdf_width=121.0)
    with pytest.raises(ValueError, match="PAGE_RENDER_GEOMETRY_MISMATCH"):
        render_review_html(_model(), tmp_path / "mismatch")

    _write_page_assets(tmp_path / "tampered")
    page = tmp_path / "tampered" / "REV1" / "page-0003.png"
    page.write_bytes(page.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="page image hash mismatch"):
        render_review_html(_model(), tmp_path / "tampered")


def test_workspace_is_offline_responsive_accessible_and_print_safe(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    for value in (
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "@media (max-width: 1100px)",
        "@media print",
        "size: A4",
        "position: sticky",
        "min-height: 44px",
        "font-size: 16px",
        "outline: 3px solid var(--focus)",
    ):
        assert value in html
    assert "https://" not in html and "http://" not in html
