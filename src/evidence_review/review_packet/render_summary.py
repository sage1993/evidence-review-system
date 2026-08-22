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


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def render_status_band(model: Mapping[str, object]) -> str:
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
    summary = _mapping(model.get("summary"))
    citation_count = summary.get("citation_count", 0)
    missing = summary.get("missing_input_count", 0)
    conflicts = summary.get("conflict_count", 0)
    exceptions = summary.get("exception_count", 0)
    additional_count = sum(
        value for value in (missing, conflicts, exceptions)
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
            '<div><dt>근거</dt><dd>', _text(citation_count), ' 건</dd></div>',
            '<div><dt>추가 확인</dt><dd>', _text(additional_count), ' 건</dd></div>',
            "</dl>",
            '<span id="ready-for-review" class="visually-hidden">',
            _text(localized_status(model.get("display_status", model.get("status")))),
            "</span>",
            "</section>",
        )
    )


def render_additional_review(model: Mapping[str, object]) -> str:
    visual_review = render_case_visual_review(model)
    items = additional_review_items(model)
    if not items:
        return visual_review
    first = _text(items[0])
    entries = "".join(f"<li>{_text(item)}</li>" for item in items)
    additional = "".join(
        (
            '<section id="additional-review" aria-labelledby="additional-heading">',
            '<div class="additional-message">', icon_svg("info", size=16),
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
    return additional + visual_review


__all__ = ["render_additional_review", "render_status_band", "render_summary"]
