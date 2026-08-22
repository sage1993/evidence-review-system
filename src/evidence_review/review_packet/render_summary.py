"""Reference-image reviewer summary and conditional sections."""
from __future__ import annotations

from collections.abc import Mapping
from html import escape

from evidence_review.review_packet.icons import icon_svg
from evidence_review.review_packet.presentation import (
    additional_review_items,
    conclusion_text,
    localized_status,
)
from evidence_review.review_packet.render_case_visual import render_case_visual_review


_VISUAL_SHELL_STYLE = """
<style>
body:has(#case-visual-review){overflow:hidden}
body:has(#case-visual-review) .app-shell{width:100%;max-width:none;height:100vh;margin:0;padding:12px}
body:has(#case-visual-review) .review-workspace{display:block;height:100%;padding:0}
body:has(#case-visual-review) .review-workspace>.visual-review-grid-span{height:100%;width:100%;min-width:0}
body:has(#case-visual-review) .review-workspace>:not(.visual-review-grid-span):not(#decision-form){display:none!important}
body:has(#case-visual-review) #case-visual-review{height:100%;min-height:0;max-height:none;margin:0}
body:has(#case-visual-review) .process-strip{display:none!important}
body:has(#case-visual-review) .case-visual-transform,
body:has(#case-visual-review) .case-visual-transform img{pointer-events:none;user-select:none;-webkit-user-select:none;-webkit-user-drag:none}
body:has(#case-visual-review) #decision-form{position:fixed;right:0;top:50%;z-index:30;width:min(380px,calc(100vw - 48px));max-height:86vh;overflow:auto;transform:translate(calc(100% - 42px),-50%);transition:transform .16s ease;box-shadow:0 12px 32px rgba(16,24,40,.18);background:#fff}
body:has(#case-visual-review) #decision-form:hover,
body:has(#case-visual-review) #decision-form:focus-within{transform:translate(0,-50%)}
body:has(#case-visual-review) #decision-form::before{content:"검토 의견";position:absolute;left:0;top:0;width:42px;height:100%;display:grid;place-items:center;writing-mode:vertical-rl;background:#f8fafc;border-right:1px solid #d0d5dd;color:#475467;font-size:11px;font-weight:700;pointer-events:none}
body:has(#case-visual-review) #decision-form>*{margin-left:42px}
@media(max-width:720px){body:has(#case-visual-review) .app-shell{padding:6px}body:has(#case-visual-review) #decision-form{width:min(340px,calc(100vw - 24px))}}
</style>
"""


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _visual_workspace(model: Mapping[str, object]) -> bool:
    return model.get("case_visual_review") is not None


def _visual_grid_span(visual_review: str) -> str:
    """Make Visual Review span and own the full parent viewport workspace."""
    if not visual_review:
        return ""
    return (
        _VISUAL_SHELL_STYLE
        + '<div class="visual-review-grid-span" '
        'style="grid-column:1/-1;width:100%;min-width:0">'
        f"{visual_review}</div>"
    )


def render_status_band(model: Mapping[str, object]) -> str:
    if _visual_workspace(model):
        return ""
    raw_status = str(model.get("display_status", model.get("status", "")))
    return "".join(
        (
            '<header id="review-status" class="status-band">',
            '<div class="status-copy"><h1>정식 근거 검토</h1></div>',
            '<div class="header-actions">',
            '<span class="status-label">검토 상태</span>',
            '<span class="status-pill" data-display-status data-display-status-mode="raw">',
            _text(raw_status),
            "</span>",
            '<button type="button" data-print>', icon_svg("printer", size=16), ' 인쇄</button>',
            "</div>",
            '<p class="warning visually-hidden">기관 최종 결정이 아닌 검토 준비 상태입니다.</p>',
            "</header>",
        )
    )


def render_summary(model: Mapping[str, object]) -> str:
    if _visual_workspace(model):
        return ""
    summary = _mapping(model.get("summary"))
    citation_count = summary.get("citation_count", 0)
    missing = summary.get("missing_input_count", 0)
    conflicts = summary.get("conflict_count", 0)
    exceptions = summary.get("exception_count", 0)
    additional_count = sum(
        value
        for value in (missing, conflicts, exceptions)
        if isinstance(value, int) and not isinstance(value, bool)
    )
    return "".join(
        (
            '<section id="review-summary" class="result-card" aria-labelledby="summary-heading">',
            '<div class="result-question-block">',
            '<span class="summary-label">질문</span>',
            f'<h2 id="summary-heading">{_text(model.get("question"))}</h2>',
            f'<span class="visually-hidden">질문 {_text(model.get("question"))}</span>',
            "</div>",
            '<div class="result-conclusion-block">',
            '<span class="summary-label">결론</span>',
            f'<p class="answer-summary">{_text(conclusion_text(model))}</p>',
            "</div>",
            '<dl class="result-facts">',
            '<div><dt>근거</dt><dd>',
            _text(citation_count),
            ' 건</dd></div>',
            '<div><dt>추가 확인</dt><dd>',
            _text(additional_count),
            ' 건</dd></div>',
            "</dl>",
            '<span id="ready-for-review" class="visually-hidden">',
            _text(localized_status(model.get("display_status", model.get("status")))),
            "</span>",
            "</section>",
        )
    )


def render_additional_review(model: Mapping[str, object]) -> str:
    visual_review = _visual_grid_span(render_case_visual_review(model))
    if visual_review:
        # In Visual Review mode the #119 workspace owns the screen. Missing inputs and
        # comparison boundaries are represented inside Findings rather than duplicated
        # in the legacy additional-review strip below the viewer.
        return visual_review
    items = additional_review_items(model)
    if not items:
        return ""
    first = _text(items[0])
    entries = "".join(f"<li>{_text(item)}</li>" for item in items)
    return "".join(
        (
            '<section id="additional-review" aria-labelledby="additional-heading">',
            '<div class="additional-message">',
            icon_svg("info", size=16),
            '<strong id="additional-heading">추가 확인</strong>',
            f'<span>{first}</span></div>',
            '<button type="button" class="additional-toggle" data-additional-toggle ',
            'aria-expanded="false" aria-controls="additional-details">자세히 보기 <span aria-hidden="true">⌄</span></button>',  # noqa: E501
            '<div id="additional-details" class="additional-details" hidden>',
            f'<ul class="attention-list">{entries}</ul>',
            "</div>",
            "</section>",
        )
    )


__all__ = ["render_additional_review", "render_status_band", "render_summary"]
