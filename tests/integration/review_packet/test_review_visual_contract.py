import re
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.review_packet.render_case_visual import (
    case_visual_css,
    render_case_visual_review,
)
from evidence_review.review_packet.render_summary import visual_shell_css
from tests.unit.review_packet.test_case_visual_renderer import _typed_reference_model

from .test_html_renderer import _model, _write_page_assets


def _inline_css(html: str) -> str:
    match = re.search(r"<style>(?P<css>.*?)</style>", html, re.DOTALL)
    assert match is not None
    return match.group("css")


def _media(css: str, marker: str) -> str:
    start = css.index(marker)
    opening = css.index("{", start)
    depth = 0
    for index in range(opening, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[opening + 1 : index]
    raise AssertionError(marker)


def test_desktop_layout_keeps_evidence_primary_and_decision_sticky(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    css = _inline_css(html)

    assert "grid-template-columns: minmax(280px, 360px) minmax(0, 1fr) minmax(320px, 360px)" in css
    assert "items viewer decision" in css
    assert '"additional additional additional"' in css
    assert "position: sticky" in css
    assert "top: 16px" in css
    assert "font-size: 16px" in css
    assert "overflow-x: hidden" in css


def test_1100_breakpoint_stacks_decision_and_preserves_min_width_zero(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    css = _inline_css(html)
    medium = _media(css, "@media (max-width: 1100px)")

    assert "grid-template-columns: minmax(0, 1fr)" in medium
    assert '"decision"' in medium
    assert "position: static" in medium
    assert "min-width: 0" in css
    assert "overflow: auto" in css


def test_accessibility_contract_has_visible_focus_and_44px_targets(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    css = _inline_css(html)

    assert "min-height: 44px" in css
    assert "outline: 3px solid var(--focus)" in css
    assert "outline-offset: 2px" in css
    assert ".evidence-page:focus-visible" in css
    assert ".pdf-page-controls button, .pdf-zoom-controls button" in css
    assert "min-height: 44px" in css
    assert "review_responsive.css" in html


def test_rendered_styles_meet_typography_and_unbounded_viewer_contract(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    css = _inline_css(html)

    assert re.search(r"font-size:\s*(?:9|10|10\.5|11)px", css) is None
    assert re.search(r"font:\s*[^;]*(?:9|10|10\.5|11)px", css) is None
    assert "min-height: 530px" not in css
    assert "max-height: 530px" not in css
    assert "width: min(100%, 720px)" not in css
    assert "height: min(72vh, 820px)" not in css


def test_workspace_loads_named_css_modules_for_each_review_region(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    for module in (
        "shell.css",
        "viewer.css",
        "issues.css",
        "decision.css",
        "audit.css",
        "responsive.css",
    ):
        assert f"/* {module} */" in html


def test_reference_viewer_preserves_split_and_responsive_contract(tmp_path: Path) -> None:
    html = render_case_visual_review(_typed_reference_model())
    css = case_visual_css() + visual_shell_css()

    assert 'data-reference-width="42"' in html
    assert 'aria-valuemin="26"' in html
    assert 'aria-valuemax="70"' in html
    assert "@media(max-width:720px)" in css


def test_print_hides_audit_navigation_and_interactive_controls(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    css = _inline_css(html)
    print_css = _media(css, "@media print")

    for selector in (
        "#packet-global-review",
        "#review-items",
        ".viewer-controls",
        ".citation-audit",
        ".item-audit",
    ):
        assert selector in print_css
    assert "display: none !important" in print_css
    assert "transform: none !important" in print_css
    assert "질문 &lt;검토 질문&gt;" in html


def test_target_desktop_viewports_remain_above_stacking_breakpoint(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    breakpoint = re.search(r"@media \(max-width: (?P<width>\d+)px\)", html)
    assert breakpoint is not None
    threshold = int(breakpoint.group("width"))
    for width, height in ((1366, 768), (1920, 1080), (3840, 2160)):
        assert width > threshold, f"{width}x{height} unexpectedly stacks"


def test_review_selection_and_focus_orchestration_is_non_recursive(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    select_start = html.index("function selectReviewItem")
    focus_start = html.index("function focusEvidence")
    resolve_start = html.index("function resolveReviewItemEvidence")
    select_body = html[select_start:focus_start]
    focus_body = html[focus_start:resolve_start]

    assert "focusEvidence(" not in select_body
    assert "selectReviewItem(" not in focus_body
    assert "function activateReviewItem" in html
    assert "window.activateReviewItem = activateReviewItem" in html
