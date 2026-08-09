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


def test_final_review_css_matches_issue_5_shell_and_grid_contract(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))

    assert ".app-shell" in css
    assert "max-width: 1700px" in css
    assert "margin: 18px auto" in css
    assert ".metrics" in css and "gap: 10px" in css
    assert ".metric" in css and "border-radius: 14px" in css
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in css
    assert ".review-item" in css and "min-height: 68px" not in css
    assert ".primary-action" in css and "align-self: stretch" not in css
    decision_form = _css_rule(css, "#decision-form form")
    assert "display: grid" in decision_form
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in decision_form
    assert "gap: 10px" in decision_form
    assert "align-items: start" in decision_form
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
