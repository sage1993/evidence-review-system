import re
from pathlib import Path

from ansim_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _model, _write_page_assets


def _inline_css(html: str) -> str:
    match = re.search(r"<style>(?P<css>.*?)</style>", html, re.DOTALL)
    assert match is not None
    return match.group("css")


def _css_rule(css: str, selector: str) -> str:
    match = re.search(
        rf"(?m)^\s*{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}",
        css,
    )
    assert match is not None
    return match.group("body")


def _media_rule(css: str, media: str) -> str:
    start = css.index(media)
    opening = css.index("{", start)
    depth = 0
    for index in range(opening, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[opening + 1 : index]
    raise AssertionError(f"unclosed media rule: {media}")


def _assert_review_viewport_budget(css: str) -> None:
    shell = _css_rule(css, ".app-shell")
    assert "max-width: 1700px" in shell
    assert "margin: 18px auto" in shell
    assert "width: calc(100% - 36px)" in shell

    metrics = _css_rule(css, ".metrics")
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in metrics
    assert "gap: 10px" in metrics

    workspace = _css_rule(css, ".review-workspace")
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in workspace

    viewer = _css_rule(css, "#evidence-viewer")
    assert "overflow: hidden" in viewer
    evidence_page = _css_rule(css, ".evidence-page")
    assert "overflow: auto" in evidence_page
    page_stage = _css_rule(css, ".page-stage")
    assert "overflow: auto" in page_stage
    detail_tabs = _css_rule(css, "#detail-tabs")
    assert "min-width: 0" in detail_tabs
    assert "overflow-x: auto" in detail_tabs

    detail_panel = _css_rule(css, ".detail-panel")
    assert "min-width: 0" in detail_panel

    table_scroll = _css_rule(css, ".table-scroll")
    assert "max-width: 100%" in table_scroll
    assert "overflow-x: auto" in table_scroll

    decision_form = _css_rule(css, "#decision-form form")
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in decision_form
    assert "align-items: start" in decision_form

    body = _css_rule(css, "body")
    assert "overflow-x: hidden" in body

    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 820px)" in css
    assert "@media (max-width: 1100px)" not in css
    medium = _media_rule(css, "@media (max-width: 1180px)")
    assert "grid-template-columns: 260px minmax(0, 1fr)" in _css_rule(
        medium, ".review-workspace"
    )
    mobile = _media_rule(css, "@media (max-width: 820px)")
    mobile_workspace = _css_rule(mobile, ".review-workspace")
    assert (
        'grid-template-areas: "summary" "items" "viewer" "detail" "global" "decision"'
        in mobile_workspace
    )
    assert "grid-template-columns: 1fr" in _css_rule(mobile, "#decision-form form")

    print_css = _media_rule(css, "@media print")
    assert "overflow: visible" in _css_rule(print_css, "#detail-tabs")
    assert "display: block" in _css_rule(print_css, ".review-workspace")
    print_evidence_page = _css_rule(print_css, ".evidence-page")
    assert "display: block !important" in print_evidence_page
    assert "overflow: visible" in print_evidence_page
    assert "overflow: visible" in _css_rule(print_css, ".page-stage")
    assert "transform: none !important" in _css_rule(print_css, ".page-canvas")
    assert "overflow: visible" in _css_rule(print_css, ".table-scroll")
    assert "display: block !important" in _css_rule(print_css, "[data-tab-panel]")


def test_final_review_css_matches_issue_5_shell_and_grid_contract(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))

    assert ".metric" in css and "border-radius: 14px" in css
    assert ".review-item" in css and "min-height: 68px" not in css
    decision_form = _css_rule(css, "#decision-form form")
    assert "display: grid" in decision_form
    assert "gap: 10px" in decision_form
    decision_actions = _css_rule(css, "#decision-form .decision-actions")
    assert "grid-column: 1 / -1" in decision_actions


def test_final_review_css_freezes_responsive_print_and_overflow_safeguards(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))

    assert re.search(r"body\s*\{[^}]*overflow-x:\s*hidden", css, re.DOTALL)
    assert re.search(r"[^}]min-width:\s*0", css)
    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 820px)" in css
    assert "@media (max-width: 1100px)" not in css
    print_css = _media_rule(css, "@media print")
    assert "#detail-tabs { overflow: visible; }" in print_css
    assert "[data-tab-panel] { display: block !important; }" in print_css


def test_final_review_css_freezes_concrete_viewport_budgets_and_print_flow(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))
    _assert_review_viewport_budget(css)


def test_final_review_print_overrides_dark_tokens_and_form_table_surfaces(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))
    print_css = _media_rule(css, "@media print")

    for token, value in (
        ("--bg", "#fff"),
        ("--shell", "#fff"),
        ("--surface", "#fff"),
        ("--surface-strong", "#fff"),
        ("--border", "#94a3b8"),
        ("--border-soft", "#cbd5e1"),
        ("--text", "#111827"),
        ("--muted", "#475569"),
    ):
        assert re.search(rf"{re.escape(token)}:\s*{re.escape(value)}", print_css)

    print_inputs = _css_rule(
        print_css,
        '#decision-form input:not([type="radio"]), #decision-form textarea',
    )
    assert "background: #fff" in print_inputs
    assert "border-color: var(--border)" in print_inputs
    assert "color: var(--text)" in print_inputs
    print_cells = _css_rule(print_css, "th, td")
    assert "border-color: var(--border)" in print_cells
    assert "color: var(--text)" in print_cells
