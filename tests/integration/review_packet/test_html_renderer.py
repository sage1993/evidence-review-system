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
        "human_decision": None,
        "decision_options": [],
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


def _decision_form_html(html: str) -> str:
    match = re.search(
        r'<section id="decision-form".*?</section>',
        html,
        re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def _packet_global_review_html(html: str) -> str:
    match = re.search(
        r'<section id="packet-global-review".*?(?=<section id="decision-form")',
        html,
        re.DOTALL,
    )
    assert match is not None
    return match.group(0)


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
    assert "기계 평가는 최종 판정이 아닙니다." in html
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


def test_detail_tabs_filter_calculations_and_rules_by_item_provenance(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    calculations = model["calculations"]
    rules = model["rules"]
    assert isinstance(calculations, list)
    assert isinstance(rules, list)
    calculations.append(
        {
            "calculation_result_id": "CAL2",
            "status": "SUCCESS",
            "formula_id": "AREA",
            "formula_version": "2",
            "substitution": "10*20",
            "display_result": "200",
            "raw_result": "200",
            "comparison": "ABOVE_THRESHOLD",
        }
    )
    rules.append(
        {
            "rule_id": "RULE2",
            "rule_version": "2",
            "status": "SATISFIED",
            "reason_codes": [],
        }
    )
    model["review_items"] = [
        {
            "item_id": "ITEM-C1",
            "claim_id": "C1",
            "calculation_ids": ["CAL1"],
            "rule_ids": ["RULE1"],
            "status": "NOT_SATISFIED",
            "completeness": "COMPLETE",
        },
        {
            "item_id": "ITEM-C2",
            "claim_id": "C1",
            "calculation_ids": ["CAL2"],
            "rule_ids": ["RULE2"],
            "status": "SATISFIED",
            "completeness": "COMPLETE",
        },
    ]

    html = render_review_html(model, tmp_path / "pages")
    panels = {
        item_id: panel
        for item_id, panel in re.findall(
            r'<article class="detail-panel(?: is-selected)?" data-item-id="([^\"]+)">'
            r"(?P<panel>.*?)"
            r'(?=<article class="detail-panel|</section><section id="packet-global-review")',
            html,
            re.DOTALL,
        )
    }

    assert set(panels) == {"ITEM-C1", "ITEM-C2"}
    assert "CAL1" in panels["ITEM-C1"]
    assert "CAL2" not in panels["ITEM-C1"]
    assert "RULE1" in panels["ITEM-C1"]
    assert "RULE2" not in panels["ITEM-C1"]
    assert "CAL2" in panels["ITEM-C2"]
    assert "CAL1" not in panels["ITEM-C2"]
    assert "RULE2" in panels["ITEM-C2"]
    assert "RULE1" not in panels["ITEM-C2"]


def test_review_workspace_inlines_responsive_print_and_offline_hooks(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")

    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert "max-width: 1700px" in html
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in html
    assert "@media (max-width: 1180px)" in html
    assert "@media (max-width: 820px)" in html
    assert "@media print" in html
    assert "@page { size: A4;" in html
    assert "https://" not in html
    assert "http://" not in html


def test_final_review_shell_freezes_korean_semantics_and_four_metric_cards(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")

    for copy in (
        "근거 검토 화면",
        "기계 평가는 최종 판정이 아닙니다",
        "검토 요약",
        "검토 항목",
        "근거 뷰어",
        "근거",
        "규칙·계산",
        "감사·예외",
    ):
        assert copy in html

    decision_form = _decision_form_html(html)
    for copy in ("검토자의 최종 결정", "결정 확정", "결정 JSON 다운로드"):
        assert copy in decision_form

    assert html.count('class="metric"') == 4
    assert "Evidence Review Workspace" not in html
    assert "Human decision" not in html
    assert "Machine evaluation is not the final decision." not in html


def _complete_domain_model() -> dict[str, object]:
    model = _model()
    calculations = model["calculations"]
    rules = model["rules"]
    assert isinstance(calculations, list)
    assert isinstance(rules, list)
    calculations.extend(
        [
            {
                "calculation_result_id": "CAL2",
                "status": "SUCCESS",
                "formula_id": "AREA",
                "formula_version": "2",
                "substitution": "10*20",
                "display_result": "200",
                "raw_result": "200",
                "comparison": "ABOVE_THRESHOLD",
            }
        ]
    )
    rules.extend(
        [
            {
                "rule_id": "RULE2",
                "rule_version": "2",
                "status": "SATISFIED",
                "reason_codes": [],
            }
        ]
    )
    model["exceptions"] = ["MISSING_REQUIRED_INPUT"]
    model["conflicts"] = ["SOURCE_CONFLICT"]
    model["abstention_reasons"] = ["TRACK_B_REJECTED"]
    model["audit"] = {
        "track_a_status": "COMPLETE",
        "track_b_status": "TRACK_B_REJECTED",
        "records": [
            {
                "audit_id": "AUDIT1",
                "item_id": "ITEM-C1",
                "status": "TRACK_B_REJECTED",
            }
        ],
    }
    model["review_items"] = [
        {
            "item_id": "ITEM-C1",
            "claim_id": "C1",
            "evidence_ids": ["E1"],
            "calculation_ids": ["CAL1"],
            "rule_ids": ["RULE1"],
            "audit_ids": ["AUDIT1"],
            "exception_codes": ["MISSING_REQUIRED_INPUT"],
            "conflict_codes": ["SOURCE_CONFLICT"],
            "status": "NOT_SATISFIED",
            "completeness": "COMPLETE",
        },
        {
            "item_id": "ITEM-C2",
            "claim_id": "C1",
            "evidence_ids": [],
            "calculation_ids": ["CAL2"],
            "rule_ids": ["RULE2"],
            "audit_ids": [],
            "exception_codes": [],
            "conflict_codes": [],
            "status": "SATISFIED",
            "completeness": "COMPLETE",
        },
    ]
    return model


def test_complete_domain_projection_is_item_scoped_across_all_detail_domains(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_complete_domain_model(), tmp_path / "pages")
    packet_global = _packet_global_review_html(html)
    panels = {
        item_id: panel
        for item_id, panel in re.findall(
            r'<article class="detail-panel(?: is-selected)?" data-item-id="([^"]+)">'
            r"(?P<panel>.*?)"
            r'(?=<article class="detail-panel|</section><section id="packet-global-review")',
            html,
            re.DOTALL,
        )
    }

    assert 'data-detail-tab="evidence"' in html
    assert 'data-detail-tab="rules-calculations"' in html
    assert 'data-detail-tab="audit-exceptions"' in html
    assert set(panels) == {"ITEM-C1", "ITEM-C2"}
    assert "E1" in panels["ITEM-C1"]
    assert "CAL1" in panels["ITEM-C1"]
    assert "RULE1" in panels["ITEM-C1"]
    assert "AUDIT1" in panels["ITEM-C1"]
    assert "MISSING_REQUIRED_INPUT" in panels["ITEM-C1"]
    assert "SOURCE_CONFLICT" in panels["ITEM-C1"]
    # The audit record itself explicitly carries ITEM-C1 ownership. The same
    # canonical string is also visible separately as a packet-global abstention reason.
    assert "TRACK_B_REJECTED" in panels["ITEM-C1"]
    assert "MISSING_REQUIRED_INPUT" not in panels["ITEM-C2"]
    assert "SOURCE_CONFLICT" not in panels["ITEM-C2"]
    assert "TRACK_B_REJECTED" not in panels["ITEM-C2"]
    assert "TRACK_B_REJECTED" in packet_global
    assert "traceability" in packet_global
    assert "MISSING_REQUIRED_INPUT" in packet_global
    assert "SOURCE_CONFLICT" in packet_global
    assert "CAL2" not in panels["ITEM-C1"]
    assert "RULE2" not in panels["ITEM-C1"]
    assert "CAL1" not in panels["ITEM-C2"]
    assert "RULE1" not in panels["ITEM-C2"]


def test_final_decision_panel_is_blank_and_machine_warning_is_unambiguous(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")

    decision_form = _decision_form_html(html)
    assert 'name="reviewer_id"' in decision_form
    assert 'name="reviewed_at"' in decision_form
    assert 'name="packet_sha256"' in decision_form
    assert 'name="notes"' in decision_form
    assert 'name="decision"' in decision_form
    assert not re.search(
        r'<option value="(?:SATISFIED|NOT_SATISFIED|CONDITIONAL|'
        r'ADDITIONAL_REVIEW_REQUIRED)"[^>]*selected',
        html,
    )
    assert "checked" not in html


def _inline_css(html: str) -> str:
    match = re.search(r"<style>(?P<css>.*?)</style>", html, re.DOTALL)
    assert match is not None
    return match.group("css")


def _css_declarations(css: str, selector: str) -> dict[str, str]:
    match = re.search(
        rf"(?m)^\s*{re.escape(selector)} \{{(?P<declarations>[^}}]+)\}}",
        css,
    )
    assert match is not None
    return {
        name.strip(): value.strip()
        for declaration in match.group("declarations").split(";")
        if ":" in declaration
        for name, value in [declaration.split(":", 1)]
    }


def test_detail_tabs_contain_wide_table_at_desktop_width_and_restore_print_flow(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    calculations = model["calculations"]
    assert isinstance(calculations, list)
    model["review_items"] = [
        {
            "item_id": "ITEM-C1",
            "claim_id": "C1",
            "calculation_ids": ["CAL1"],
            "rule_ids": ["RULE1"],
            "status": "NOT_SATISFIED",
            "completeness": "COMPLETE",
        }
    ]
    wide_substitution = "W" * 104
    calculations[0]["substitution"] = wide_substitution

    html = render_review_html(model, tmp_path / "pages")
    css = _inline_css(html)
    workspace = _css_declarations(css, ".review-workspace")
    detail_tabs = _css_declarations(css, "#detail-tabs")
    table = _css_declarations(css, "table")
    print_css = re.search(r"@media print \{(?P<rules>.*?)^\}", css, re.DOTALL | re.MULTILINE)
    assert print_css is not None
    print_detail_tabs = _css_declarations(print_css.group("rules"), "#detail-tabs")

    assert f"<td>{wide_substitution}</td>" in html
    assert table["width"] == "100%"
    assert detail_tabs["grid-area"] == "detail"
    assert detail_tabs["min-width"] == "0"
    assert detail_tabs.get("overflow-x") == "auto"
    assert print_detail_tabs["overflow"] == "visible"

    assert workspace["grid-template-columns"] == "260px minmax(450px, 1fr) 330px"
    assert workspace["gap"] == "12px"


@pytest.mark.parametrize(
    ("viewport", "width", "height"),
    (("1366x768", 1366, 768), ("1920x1080", 1920, 1080), ("3840x2160", 3840, 2160)),
)
def test_static_css_contract_keeps_desktop_and_print_hooks_for_target_viewports(
    tmp_path: Path, viewport: str, width: int, height: int
) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    stacked = re.search(r"@media \(max-width: (?P<width>\d+)px\)", html)
    assert stacked is not None
    assert viewport == f"{width}x{height}"
    assert width > int(stacked.group("width"))
    assert "max-width: 1700px" in html
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in html
    assert "@media print" in html
    assert "@page { size: A4;" in html


def test_review_html_refuses_missing_page_assets(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="verified page image"):
        render_review_html(_model(), tmp_path / "pages")


def test_review_html_rejects_tampered_page_image(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    page = tmp_path / "pages" / "REV1" / "page-0003.png"
    page.write_bytes(page.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="page image hash mismatch"):
        render_review_html(_model(), tmp_path / "pages")
