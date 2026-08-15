from __future__ import annotations

import re
from importlib.resources import files

import pytest


def _css_rule(css: str, selector: str, *, require_once: bool = False) -> str:
    matches = list(
        re.finditer(
        rf"(?m)^\s*{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}",
        css,
        )
    )
    assert matches, f"missing CSS rule: {selector}"
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


def _assert_annotation_print_full_flow(css: str) -> None:
    hidden = _css_rule(css, "[hidden]", require_once=True)
    assert "display: none !important" in hidden

    print_css = _media_rule(css, "@media print")
    tab_panels = _css_rule(
        print_css,
        "[data-tab-panel], [data-workspace-pane]",
        require_once=True,
    )
    assert "display: block !important" in tab_panels

    print_detail = _css_rule(print_css, ".detail-panel", require_once=True)
    assert "max-height: none" in print_detail
    assert "overflow: visible" in print_detail
    assert "overflow: visible" in _css_rule(
        print_css, ".tab-pane", require_once=True
    )

    print_shell = _css_rule(print_css, ".app-shell", require_once=True)
    assert "overflow: visible" in print_shell
    assert "overflow: visible" in _css_rule(
        print_css, ".candidate-panel", require_once=True
    )
    print_candidates = _css_rule(
        print_css, ".candidate-list", require_once=True
    )
    assert "max-height: none" in print_candidates
    assert "overflow: visible" in print_candidates

    print_stage = _css_rule(print_css, ".drawing-stage", require_once=True)
    assert "height: auto" in print_stage
    assert "min-height: 0" in print_stage
    assert "overflow: visible" in print_stage


def _assert_annotation_viewport_budget(css: str) -> None:
    shell = _css_rule(css, ".app-shell")
    assert "width: calc(100% - 36px)" in shell
    assert "max-width: 1700px" in shell
    assert "margin: 18px auto" in shell

    metrics = _css_rule(css, ".metrics")
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in metrics
    assert "gap: 10px" in metrics
    assert "border-radius: 14px" in _css_rule(css, ".metric", require_once=True)

    main_grid = _css_rule(css, ".main-grid")
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in main_grid

    stage = _css_rule(css, ".drawing-stage")
    assert "height: min(52vw, 690px)" in stage
    assert "min-height: 510px" in stage
    assert "overflow: auto" in stage

    detail = _css_rule(css, ".detail-panel")
    assert "max-height: 760px" in detail
    assert "align-self: start" in detail
    assert "overflow: hidden" in detail

    candidate_list = _css_rule(css, ".candidate-list")
    assert "max-height: 650px" in candidate_list
    assert "overflow: auto" in candidate_list

    primary_action = _css_rule(css, ".primary-action")
    assert "align-self: end" in primary_action
    assert "min-width: 150px" in primary_action

    status_strip = _css_rule(css, ".status-strip", require_once=True)
    assert "min-height: 34px" in status_strip
    assert "padding: 8px 18px" in status_strip
    desktop = _media_rule(css, "@media screen and (min-width: 1181px)")
    desktop_status_strip = _css_rule(desktop, ".status-strip", require_once=True)
    assert "min-height: 28px" in desktop_status_strip
    assert "padding: 4px 18px" in desktop_status_strip

    body = _css_rule(css, "body")
    assert "overflow-x: hidden" in body

    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 820px)" in css
    assert "@media (max-width: 1100px)" not in css

    medium = _media_rule(css, "@media (max-width: 1180px)")
    medium_grid = _css_rule(medium, ".main-grid")
    assert "grid-template-columns: 260px minmax(420px, 1fr)" in medium_grid
    assert "grid-column: 1 / -1" in _css_rule(medium, ".detail-panel")

    mobile = _media_rule(css, "@media (max-width: 820px)")
    assert "display: block" in _css_rule(mobile, ".main-grid")
    assert "grid-template-columns: 1fr 1fr" in _css_rule(mobile, ".metrics")
    assert "flex-direction: column" in _css_rule(mobile, ".status-strip")

    print_css = _media_rule(css, "@media print")
    assert "min-height: 0" in _css_rule(print_css, ".drawing-stage")
    print_controls = _css_rule(
        print_css, ".topbar-actions, .mode-switch, .primary-action, .button-row"
    )
    assert "display: none" in print_controls
    _assert_annotation_print_full_flow(css)


def test_annotation_css_matches_issue_5_visual_contract() -> None:
    css = (
        files("evidence_review.drawing_review")
        .joinpath("assets", "annotation.css")
        .read_text(encoding="utf-8")
    )

    assert ".feature" in css and "min-height: 68px" not in css
    assert ".tab-pane" in css and "overflow-y: auto" in css


def test_annotation_css_freezes_concrete_viewport_budgets_and_print_flow() -> None:
    css = (
        files("evidence_review.drawing_review")
        .joinpath("assets", "annotation.css")
        .read_text(encoding="utf-8")
    )
    _assert_annotation_viewport_budget(css)


def test_annotation_print_full_flow_rejects_selector_mutations() -> None:
    css = (
        files("evidence_review.drawing_review")
        .joinpath("assets", "annotation.css")
        .read_text(encoding="utf-8")
    )
    mutations = (
        (
            "[data-tab-panel], [data-workspace-pane] { "
            "display: block !important; }",
            "[data-tab-panel], [data-workspace-pane] { "
            "display: none !important; }",
        ),
        (
            ".detail-panel { max-height: none; overflow: visible; }",
            ".detail-panel { max-height: 760px; overflow: hidden; }",
        ),
        (
            ".candidate-list { max-height: none; overflow: visible; }",
            ".candidate-list { max-height: 650px; overflow: auto; }",
        ),
        (
            ".drawing-stage { height: auto; min-height: 0; overflow: visible;",
            ".drawing-stage { height: min(52vw, 690px); min-height: 0; overflow: auto;",
        ),
    )

    for expected, mutation in mutations:
        assert expected in css
        with pytest.raises(AssertionError):
            _assert_annotation_print_full_flow(css.replace(expected, mutation, 1))
