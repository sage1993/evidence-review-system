from __future__ import annotations

from importlib.resources import files


def test_annotation_css_matches_issue_5_visual_contract() -> None:
    css = (
        files("ansim_review.drawing_review")
        .joinpath("assets", "annotation.css")
        .read_text(encoding="utf-8")
    )

    assert ".app-shell" in css and "max-width: 1700px" in css
    assert ".metrics" in css and "gap: 10px" in css
    assert ".metric" in css and "border-radius: 14px" in css
    assert "grid-template-columns: 260px minmax(450px, 1fr) 330px" in css
    assert ".feature" in css and "min-height: 68px" not in css
    assert ".primary-action" in css and "align-self: stretch" not in css
    assert ".detail-panel" in css and "max-height: 760px" in css
    assert ".tab-pane" in css and "overflow-y: auto" in css
    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 820px)" in css
