from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.review_packet.render_case_visual import render_case_visual_review
from evidence_review.review_packet.render_summary import render_status_band
from tests.unit.review_packet.test_case_visual_renderer import _model
from tests.unit.review_packet.test_unified_workspace_renderer import _generic_model


class _RenderedDom(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {key: value or "" for key, value in attrs}))


def _canonical_css() -> str:
    assets = Path(__file__).parents[3] / "src" / "evidence_review" / "review_packet" / "assets"
    return "\n".join(
        (assets / name).read_text(encoding="utf-8")
        for name in (
            "shell.css",
            "viewer.css",
            "issues.css",
            "decision.css",
            "audit.css",
            "responsive.css",
        )
    )


def test_case_visual_fragment_has_no_inline_behavior_or_style_dom_nodes() -> None:
    parser = _RenderedDom()
    parser.feed(render_case_visual_review(_model()))

    assert sum(tag == "script" for tag, _attrs in parser.tags) == 0
    assert sum(tag == "style" for tag, _attrs in parser.tags) == 0


def test_unified_shell_has_one_capability_driven_layout_and_no_legacy_css_cascade(
    tmp_path: Path,
) -> None:
    html = render_review_html(_generic_model(), tmp_path)

    assert 'data-review-workspace="unified"' in html
    assert 'data-review-shell="unified"' in html
    assert "data-review-workspace-mode" not in html
    assert "reference-subject" not in html
    assert "reference-only" not in html
    assert "review.css" not in html
    assert "review_responsive.css" not in html

    css = _canonical_css()
    selectors = (
        ".review-workspace",
        "#decision-form",
        ".page-canvas",
        ".status-band",
        ".result-card",
    )
    for selector in selectors:
        assert len(re.findall(rf"(?m)^{re.escape(selector)}\s*\{{", css)) == 1


def test_machine_status_and_audit_are_non_authoritative_by_default() -> None:
    status = render_status_band(_generic_model())
    assert 'data-display-status-mode="localized"' in status
    assert "PARTIALLY_RESOLVED" not in status

    audit = render_review_html(_generic_model(), Path(":memory:"))
    audit_start = audit.index('<details id="packet-global-review"')
    audit_end = audit.index("</details>", audit_start)
    assert " open" not in audit[audit_start:audit_end]
