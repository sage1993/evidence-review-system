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
