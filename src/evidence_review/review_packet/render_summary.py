"""Reference-image reviewer summary and conditional sections."""
from __future__ import annotations

from collections.abc import Mapping
from html import escape

from evidence_review.review_packet.icons import icon_svg
from evidence_review.review_packet.presentation import (
    additional_review_items,
    conclusion_text,
    localized_status,
    machine_status,
    summary_attention_items,
)
from evidence_review.review_packet.render_case_visual_lazy import render_case_visual_review

# ruff: noqa: E501


_VISUAL_SHELL_STYLE = """
body:has(.review-workspace:not([data-review-shell="unified"]) #case-visual-review){overflow:hidden}
body:has(.review-workspace:not([data-review-shell="unified"]) #case-visual-review) .app-shell{width:100%;max-width:none;height:100vh;margin:0;padding:12px}
body:has(#case-visual-review) .review-workspace:not([data-review-shell="unified"]){display:block;height:100%;padding:0}
body:has(#case-visual-review) .review-workspace:not([data-review-shell="unified"])>.visual-review-grid-span{height:100%;width:100%;min-width:0}
body:has(#case-visual-review) .review-workspace>:not(.review-shell-region):not(.visual-review-grid-span):not(#decision-form){display:none!important}
body:has(#case-visual-review) .review-workspace:not([data-review-shell="unified"]) #case-visual-review{height:100%;min-height:0;max-height:none;margin:0}
body:has(#case-visual-review) .process-strip{display:none!important}
body:has(#case-visual-review) .case-visual-transform{user-select:none;-webkit-user-select:none}
@media(min-width:2560px){
body:has(#case-visual-review) .workspace-grid{grid-template-columns:minmax(0,1fr) minmax(380px,420px)}
body:has(#case-visual-review) .reference-viewer,body:has(#case-visual-review) .subject-viewer{grid-template-rows:52px minmax(0,1fr)}
body:has(#case-visual-review) .findings-panel{grid-template-rows:52px 44px minmax(0,1fr)}
body:has(#case-visual-review) .reference-viewer>header,body:has(#case-visual-review) .findings-panel>header,body:has(#case-visual-review) .subject-toolbar{padding:0 16px;font-size:14px}
body:has(#case-visual-review) .reference-viewer header span,body:has(#case-visual-review) .findings-panel header span,body:has(#case-visual-review) .subject-toolbar span{font-size:12px}
body:has(#case-visual-review) .overlay-modes button{height:34px;padding:0 10px;font-size:12px}
body:has(#case-visual-review) .viewer-controls button{width:36px;height:36px}
body:has(#case-visual-review) .toolbar-icon{width:18px;height:18px}
body:has(#case-visual-review) .finding-filter{height:34px;padding:0 9px;font-size:12px}
body:has(#case-visual-review) .findings-body{padding:10px;gap:9px}
body:has(#case-visual-review) .finding-card{padding:12px}
body:has(#case-visual-review) .finding-number,body:has(#case-visual-review) .finding-status{font-size:12px}
body:has(#case-visual-review) .finding-card h3{font-size:15px}
body:has(#case-visual-review) .comparison-grid dt{font-size:12px}
body:has(#case-visual-review) .comparison-grid dd{font-size:12.5px}
body:has(#case-visual-review) .case-visual-help{padding:7px 16px;font-size:12px}
}
@media(min-width:3200px){
body:has(#case-visual-review) .workspace-grid{grid-template-columns:minmax(0,1fr) minmax(600px,660px)}
body:has(#case-visual-review) .reference-viewer,body:has(#case-visual-review) .subject-viewer{grid-template-rows:68px minmax(0,1fr)}
body:has(#case-visual-review) .findings-panel{grid-template-rows:68px 56px minmax(0,1fr)}
body:has(#case-visual-review) .reference-viewer>header,body:has(#case-visual-review) .findings-panel>header,body:has(#case-visual-review) .subject-toolbar{padding:0 20px;font-size:17px}
body:has(#case-visual-review) .reference-viewer header span,body:has(#case-visual-review) .findings-panel header span,body:has(#case-visual-review) .subject-toolbar span{font-size:14px}
body:has(#case-visual-review) .reference-body{padding:18px}
body:has(#case-visual-review) .reference-empty{font-size:15px}
body:has(#case-visual-review) .reference-empty strong{font-size:17px}
body:has(#case-visual-review) .reference-empty p{max-width:440px;line-height:1.6}
body:has(#case-visual-review) .reference-kind{padding:5px 9px;font-size:13px}
body:has(#case-visual-review) .reference-card{padding:16px;margin-bottom:12px}
body:has(#case-visual-review) .reference-source{font-size:13px}
body:has(#case-visual-review) .reference-card blockquote{font-size:15px}
body:has(#case-visual-review) .related-reference summary{font-size:14px}
body:has(#case-visual-review) .overlay-modes button{height:42px;padding:0 13px;font-size:14px}
body:has(#case-visual-review) .viewer-controls{gap:8px}
body:has(#case-visual-review) .viewer-controls button{width:48px;height:48px}
body:has(#case-visual-review) .toolbar-icon{width:22px;height:22px}
body:has(#case-visual-review) .control-separator{height:26px;margin:0 5px}
body:has(#case-visual-review) .finding-filters{gap:6px;padding:7px 10px}
body:has(#case-visual-review) .finding-filter{height:42px;padding:0 12px;font-size:14px}
body:has(#case-visual-review) .findings-body{padding:14px;gap:12px}
body:has(#case-visual-review) .finding-card{padding:16px;border-radius:12px}
body:has(#case-visual-review) .finding-number,body:has(#case-visual-review) .finding-status{font-size:14px}
body:has(#case-visual-review) .finding-status{padding:5px 9px}
body:has(#case-visual-review) .finding-card h3{font-size:18px;margin:10px 0 9px}
body:has(#case-visual-review) .comparison-grid{gap:8px}
body:has(#case-visual-review) .comparison-grid div{padding:9px 10px}
body:has(#case-visual-review) .comparison-grid dt{font-size:13px;margin-bottom:4px}
body:has(#case-visual-review) .comparison-grid dd{font-size:15px;line-height:1.45}
body:has(#case-visual-review) .case-visual-help{padding:9px 20px;font-size:14px}
}
@media(max-width:720px){body:has(#case-visual-review) .app-shell{padding:6px}}
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
        '<div class="visual-review-grid-span" '
        '>'
        f"{visual_review}</div>"
    )


def visual_shell_css() -> str:
    """Return visual-shell layout CSS for the document-level stylesheet."""
    return _VISUAL_SHELL_STYLE


def render_status_band(model: Mapping[str, object]) -> str:
    raw_status = machine_status(model)
    return "".join(
        (
            '<header id="review-status" class="status-band">',
            '<div class="status-copy"><h1>정식 근거 검토</h1></div>',
            '<div class="header-actions">',
            '<span class="status-label">기계 검토 결과</span>',
            '<span class="status-pill" data-machine-status data-display-status '
            'data-display-status-mode="localized">',
            _text(localized_status(raw_status)),
            "</span>",
            '<button type="button" data-print>', icon_svg("printer", size=16), ' 인쇄</button>',
            "</div>",
            '<p class="warning visually-hidden">기관 최종 결정이 아닌 검토 준비 상태입니다.</p>',
            "</header>",
        )
    )


def render_summary(model: Mapping[str, object]) -> str:
    summary = _mapping(model.get("summary"))
    citation_count = summary.get("citation_count", 0)
    missing = summary.get("missing_input_count", 0)
    conflicts = summary.get("conflict_count", 0)
    exceptions = summary.get("exception_count", 0)
    attention_items = summary_attention_items(model)
    additional_count = (
        len(attention_items)
        if model.get("issue_results")
        else sum(
            value
            for value in (missing, conflicts, exceptions)
            if isinstance(value, int) and not isinstance(value, bool)
        )
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
            '<div><dt>인용 근거</dt><dd>',
            _text(citation_count),
            '건</dd></div>',
            '<div><dt>추가 확인 항목</dt><dd>',
            _text(additional_count),
            '건</dd></div>',
            "</dl>",
            _summary_attention(attention_items),
            "</section>",
        )
    )


def _summary_attention(items: tuple[str, ...]) -> str:
    """Keep the first packet-backed blocker visible without burying the comparison."""
    if not items:
        return ""
    primary, *remaining = items
    content = (
        '<section id="summary-attention" aria-labelledby="summary-attention-heading">'
        '<h3 id="summary-attention-heading">추가 확인이 필요한 항목</h3>'
        f'<p class="summary-attention-primary">{_text(primary)}</p>'
    )
    if remaining:
        content += (
            '<details class="summary-attention-details">'
            f'<summary>추가 확인 항목 {len(remaining)}건 보기</summary><ul>'
            + "".join(f"<li>{_text(item)}</li>" for item in remaining)
            + "</ul></details>"
        )
    return content + "</section>"


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
            'aria-expanded="false" aria-controls="additional-details">자세히 보기 <span aria-hidden="true">⌄</span></button>',
            '<div id="additional-details" class="additional-details" hidden>',
            f'<ul class="attention-list">{entries}</ul>',
            "</div>",
            "</section>",
        )
    )


__all__ = [
    "render_additional_review",
    "render_status_band",
    "render_summary",
    "visual_shell_css",
]
