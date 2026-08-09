import re
from pathlib import Path

from ansim_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _model, _write_page_assets


def test_review_workspace_escapes_user_content_and_has_blank_offline_controls(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    model["question"] = '<img src=x onerror="alert(1)">&\u2028'
    model["abstention_reasons"] = ["<unresolved evidence>"]
    model["review_items"] = [
        {
            "item_id": "ITEM-C1",
            "claim_id": "C1",
            "status": "INDETERMINATE",
            "completeness": "INCOMPLETE",
        }
    ]

    html = render_review_html(model, tmp_path / "pages")

    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;' in html
    assert '<img src=x onerror="alert(1)">' not in html
    assert "\\u003cimg" in html
    assert "\\u003e" in html
    assert "\\u0026" in html
    assert "\\u2028" in html
    assert 'id="ready-for-review"' in html
    assert 'id="abstention-reasons"' in html
    assert 'name="decision"' in html
    assert "checked" not in html
    assert 'fetch("./decision"' in html
    assert "https://" not in html
    assert "http://" not in html
    for function_name in (
        "selectReviewItem",
        "activateDetailTab",
        "focusEvidence",
        "setEvidenceZoom",
        "submitDecision",
        "downloadDecisionEnvelope",
    ):
        assert function_name in html


def test_review_workspace_zoom_transforms_the_shared_page_canvas(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")

    assert 'document.querySelectorAll(".page-canvas")' in html
    assert 'canvas.style.transform = "scale(" + scale + ")"' in html
    assert 'document.querySelectorAll(".evidence-page img")' not in html


def test_review_workspace_decision_envelope_matches_the_protected_route_contract(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")
    match = re.search(
        r"function decisionEnvelope\(form\) \{.*?return \{(?P<fields>.*?)\n    \};",
        html,
        re.DOTALL,
    )

    assert match is not None
    assert re.findall(r"^      ([a-z_]+):", match.group("fields"), re.MULTILINE) == [
        "reviewer_id",
        "reviewed_at",
        "packet_hash",
        "decision",
        "notes",
    ]


def test_review_workspace_localizes_compact_final_decision_controls_without_selection(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")

    assert "검토자의 최종 결정" in html
    assert "결정 확정" in html
    assert "결정 JSON 다운로드" in html
    assert "기계 평가는 최종 결정이 아닙니다" in html
    assert not re.search(
        r'<option value="(?:SATISFIED|NOT_SATISFIED|CONDITIONAL|'
        r'ADDITIONAL_REVIEW_REQUIRED)"[^>]*selected',
        html,
    )
    assert "checked" not in html
