import re
from pathlib import Path

from ansim_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _model, _write_page_assets


def _inline_css(html: str) -> str:
    match = re.search(r"<style>(?P<css>.*?)</style>", html, re.DOTALL)
    assert match is not None
    return match.group("css")


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
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert "#decision-form" in css


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
    assert "@media print" in css
    assert "#detail-tabs { overflow: visible; }" in css
    assert "[data-tab-panel] { display: block !important; }" in css

