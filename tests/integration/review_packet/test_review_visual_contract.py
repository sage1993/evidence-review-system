import re
from pathlib import Path

import pytest

from ansim_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import (
    _model,
    _populated_global_audit_model,
    _write_page_assets,
)


def _inline_css(html: str) -> str:
    match = re.search(r"<style>(?P<css>.*?)</style>", html, re.DOTALL)
    assert match is not None
    return match.group("css")


def _css_rule(css: str, selector: str, *, require_once: bool = False) -> str:
    matches = list(
        re.finditer(
        rf"(?m)^\s*{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}",
        css,
        )
    )
    assert matches
    if require_once:
        top_level = [
            match
            for match in matches
            if css[: match.start()].count("{") == css[: match.start()].count("}")
        ]
        assert len(top_level) == 1, f"expected one top-level CSS rule: {selector}"
    return matches[0].group("body")


def _media_rule(css: str, media: str) -> str:
    assert css.count(media) == 1, f"expected one media block: {media}"
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
    assert "border-radius: 14px" in _css_rule(css, ".metric", require_once=True)

    workspace = _css_rule(css, ".review-workspace")
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in workspace

    viewer = _css_rule(css, "#evidence-viewer")
    assert "overflow: hidden" in viewer
    evidence_page = _css_rule(css, ".evidence-page", require_once=True)
    assert "overflow: auto" in evidence_page
    page_stage = _css_rule(css, ".page-stage", require_once=True)
    assert "overflow: auto" in page_stage
    detail_tabs = _css_rule(css, "#detail-tabs")
    assert "min-width: 0" in detail_tabs
    assert "overflow-x: auto" in detail_tabs

    detail_panel = _css_rule(css, ".detail-panel")
    assert "min-width: 0" in detail_panel

    table_scroll = _css_rule(css, ".table-scroll")
    assert "max-width: 100%" in table_scroll
    assert "overflow-x: auto" in table_scroll

    decision_form = _css_rule(css, "#decision-form form", require_once=True)
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
    print_evidence_page = _css_rule(
        print_css, ".evidence-page", require_once=True
    )
    assert "display: block !important" in print_evidence_page
    assert "overflow: visible" in print_evidence_page
    assert "overflow: visible" in _css_rule(
        print_css, ".page-stage", require_once=True
    )
    assert "transform: none !important" in _css_rule(
        print_css, ".page-canvas", require_once=True
    )
    assert "overflow: visible" in _css_rule(print_css, ".table-scroll")
    assert "display: block !important" in _css_rule(print_css, "[data-tab-panel]")


def _assert_populated_global_card_budget(css: str) -> None:
    base_card = _css_rule(css, ".global-card", require_once=True)
    assert "max-height: none" in base_card
    assert "overflow: visible" in base_card
    assert "overflow-wrap: anywhere" in base_card

    desktop = _media_rule(css, "@media screen and (min-width: 1181px)")
    desktop_card = _css_rule(desktop, ".global-card", require_once=True)
    assert "max-height: 96px" in desktop_card
    assert "overflow: auto" in desktop_card

    medium = _media_rule(css, "@media (max-width: 1180px)")
    medium_card = _css_rule(medium, ".global-card", require_once=True)
    assert "max-height: none" in medium_card
    assert "overflow: visible" in medium_card

    print_css = _media_rule(css, "@media print")
    print_card = _css_rule(print_css, ".global-card", require_once=True)
    assert "max-height: none" in print_card
    assert "overflow: visible" in print_card


def test_final_review_css_matches_issue_5_shell_and_grid_contract(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))

    assert ".review-item" in css and "min-height: 68px" not in css
    decision_form = _css_rule(css, "#decision-form form")
    assert "display: grid" in decision_form
    assert "gap: 4px" in decision_form
    decision_actions = _css_rule(css, "#decision-form .decision-actions")
    assert "grid-column: 1 / -1" in decision_actions


def test_final_decision_panel_uses_compact_three_column_desktop_budget(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))

    heading = _css_rule(css, ".decision-heading", require_once=True)
    assert "padding: 6px 10px" in heading

    form = _css_rule(css, "#decision-form form", require_once=True)
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in form
    assert "gap: 4px" in form
    assert "padding: 6px 10px" in form

    choices = _css_rule(css, ".decision-choices", require_once=True)
    assert "gap: 3px" in choices
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in choices
    assert "margin-bottom: 2px" in _css_rule(
        css, ".decision-choices legend", require_once=True
    )
    option = _css_rule(css, ".decision-option", require_once=True)
    assert "min-height: 24px" in option
    assert "padding: 4px 5px" in option

    fields = _css_rule(css, ".decision-fields", require_once=True)
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in fields
    assert "gap: 3px" in fields
    controls = _css_rule(
        css,
        "#decision-form input:not([type=\"radio\"]), #decision-form textarea",
        require_once=True,
    )
    assert "min-height: 30px" in controls
    assert "padding: 4px 6px" in controls
    notes = _css_rule(css, ".decision-notes textarea", require_once=True)
    assert "min-height: 42px" in notes

    actions = _css_rule(css, "#decision-form .decision-actions", require_once=True)
    assert "align-items: end" in actions
    primary_action = _css_rule(css, ".primary-action", require_once=True)
    assert "align-self: end" in primary_action
    assert "align-self: stretch" not in primary_action


def test_global_audit_and_decision_sections_use_the_second_round_compact_budget(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))

    audit = _css_rule(css, "#packet-global-review", require_once=True)
    assert "padding: 8px 12px" in audit
    audit_grid = _css_rule(css, ".global-review-grid", require_once=True)
    assert "gap: 6px" in audit_grid
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in audit_grid
    audit_card = _css_rule(css, ".global-card", require_once=True)
    assert "align-content: start" in audit_card
    assert "display: grid" in audit_card
    assert "gap: 2px" in audit_card
    assert "padding: 6px 8px" in audit_card
    assert "overflow: hidden" not in audit_card
    assert "margin: 0" in _css_rule(
        css, "#packet-global-review .empty-state", require_once=True
    )

    empty_status = _css_rule(css, ".form-status:empty", require_once=True)
    assert "display: none" in empty_status


def test_desktop_primary_workflow_uses_the_third_round_vertical_budget(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    css = _inline_css(html)

    assert 'class="global-audit-layout"' in html

    status_band = _css_rule(css, ".status-band", require_once=True)
    assert "padding: 10px 14px" in status_band

    shell = _css_rule(css, ".app-shell", require_once=True)
    assert "margin: 18px auto" in shell

    workspace = _css_rule(css, ".review-workspace", require_once=True)
    assert "gap: 6px" in workspace
    assert "padding: 8px 18px 0" in workspace
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in workspace

    audit_layout = _css_rule(css, ".global-audit-layout", require_once=True)
    assert "display: grid" in audit_layout
    assert "gap: 10px" in audit_layout
    assert "grid-template-columns: 210px minmax(0, 1fr)" in audit_layout
    assert "margin: 0" in _css_rule(
        css, ".global-audit-layout .section-heading", require_once=True
    )

    action_buttons = _css_rule(
        css, "#decision-form .decision-actions button", require_once=True
    )
    assert "padding: 5px 9px" in action_buttons
    process_strip = _css_rule(css, ".process-strip", require_once=True)
    assert "gap: 4px" in process_strip
    assert "padding: 3px 12px 2px" in process_strip

    medium = _media_rule(css, "@media (max-width: 1180px)")
    medium_workspace = _css_rule(medium, ".review-workspace")
    assert "gap: 12px" in medium_workspace
    assert "padding: 14px 18px 12px" in medium_workspace
    assert "display: block" in _css_rule(
        medium, ".global-audit-layout", require_once=True
    )
    assert "padding: 4px 12px 5px" in _css_rule(
        medium, ".process-strip", require_once=True
    )

    mobile = _media_rule(css, "@media (max-width: 820px)")
    assert "gap: 8px" in _css_rule(mobile, ".review-workspace")


def test_populated_global_audit_cards_use_bounded_desktop_internal_scrolling(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_populated_global_audit_model(), tmp_path / "pages")
    css = _inline_css(html)

    assert html.count('class="global-card"') == 4
    for value in (
        "AUDIT3",
        "CITATION_COORDINATE_CONFLICT",
        "LOW_CONFIDENCE",
        "rule_coverage",
        "test-fixture-rule-results",
    ):
        assert value in html
    _assert_populated_global_card_budget(css)


def test_populated_global_audit_card_budget_rejects_cascade_mutations(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(
        render_review_html(_populated_global_audit_model(), tmp_path / "pages")
    )

    for override in (
        ".global-card { max-height: none; overflow: visible; }",
        (
            "@media screen and (min-width: 1181px) { "
            ".global-card { max-height: none; overflow: visible; } }"
        ),
        (
            "@media (max-width: 1180px) { "
            ".global-card { max-height: 96px; overflow: auto; } }"
        ),
        "@media print { .global-card { max-height: 96px; overflow: auto; } }",
    ):
        with pytest.raises(AssertionError):
            _assert_populated_global_card_budget(css + "\n" + override)


def test_final_review_css_freezes_concrete_viewport_budgets_and_print_flow(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))
    _assert_review_viewport_budget(css)


def test_final_review_css_rejects_later_equal_specificity_viewport_overrides(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    css = _inline_css(render_review_html(_model(), tmp_path / "pages"))

    for override in (
        ".evidence-page { overflow: hidden; }",
        "#decision-form form { align-items: stretch; }",
        "@media print { .page-canvas { transform: scale(2) !important; } }",
    ):
        with pytest.raises(AssertionError):
            _assert_review_viewport_budget(css + "\n" + override)


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
