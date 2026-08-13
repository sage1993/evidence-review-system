"""Reviewer-facing summary and conditional sections."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape

from ansim_review.review_packet.presentation import (
    additional_review_items,
    conclusion_text,
    localized_status,
)


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def render_status_band(model: Mapping[str, object]) -> str:
    status = localized_status(model.get("display_status", model.get("status")))
    return "".join(
        (
            '<header id="review-status" class="status-band">',
            '<div class="status-copy">',
            '<span class="eyebrow">정식 근거 검토</span>',
            '<div class="status-line"><span class="status-pill" data-display-status>',
            _text(status),
            "</span></div>",
            '<h1>검토 결과</h1>',
            f'<p class="question-context">{_text(model.get("question"))}</p>',
            "</div>",
            '<div class="header-actions"><button type="button" data-print>인쇄</button></div>',
            '<p class="warning">기계 검토 결과이며, 최종 판정은 검토자가 확정합니다.</p>',
            "</header>",
        )
    )


def render_summary(model: Mapping[str, object]) -> str:
    summary = _mapping(model.get("summary"))
    status = localized_status(model.get("display_status", model.get("status")))
    citation_count = summary.get("citation_count", 0)
    missing = summary.get("missing_input_count", 0)
    conflicts = summary.get("conflict_count", 0)
    exceptions = summary.get("exception_count", 0)
    additional_count = 0
    for value in (missing, conflicts, exceptions):
        if isinstance(value, int) and not isinstance(value, bool):
            additional_count += value
    return "".join(
        (
            '<section id="review-summary" class="result-card" aria-labelledby="summary-heading">',
            '<div class="result-main">',
            '<span class="section-kicker">1. 검토 결과</span>',
            f'<p class="result-question"><strong>질문</strong> {_text(model.get("question"))}</p>',
            '<h2 id="summary-heading" data-display-status>',
            _text(status),
            "</h2>",
            f'<p class="result-conclusion">{_text(conclusion_text(model))}</p>',
            "</div>",
            '<dl class="result-facts">',
            '<div><dt>연결 근거</dt><dd>',
            _text(citation_count),
            "건</dd></div>",
            '<div><dt>추가 확인</dt><dd>',
            _text(additional_count),
            "건</dd></div>",
            "</dl>",
            '<span id="ready-for-review" class="visually-hidden">',
            _text(status),
            "</span>",
            "</section>",
        )
    )


def render_review_item_navigation(items: Sequence[Mapping[str, object]]) -> str:
    """Hide the navigator for the common one-claim case."""
    if len(items) <= 1:
        return ""
    buttons: list[str] = []
    for index, item in enumerate(items):
        status = localized_status(item.get("status"))
        buttons.append(
            "".join(
                (
                    '<button class="review-item',
                    " is-selected" if index == 0 else "",
                    '" type="button" data-item-id="',
                    _text(item.get("item_id")),
                    '" aria-pressed="',
                    "true" if index == 0 else "false",
                    '"><strong>검토 항목 ',
                    str(index + 1),
                    "</strong><span>",
                    _text(status),
                    "</span></button>",
                )
            )
        )
    return "".join(
        (
            '<nav id="review-items" aria-label="검토 항목 선택">',
            '<div class="panel-heading"><h2>검토 항목</h2><span>',
            str(len(items)),
            "건</span></div>",
            '<div class="review-item-list">',
            "".join(buttons),
            "</div></nav>",
        )
    )


def render_additional_review(model: Mapping[str, object]) -> str:
    items = additional_review_items(model)
    if not items:
        return ""
    entries = "".join(f"<li>{_text(item)}</li>" for item in items)
    return "".join(
        (
            '<section id="additional-review" aria-labelledby="additional-heading">',
            '<span class="section-kicker">3. 추가 확인</span>',
            '<h2 id="additional-heading">확인이 필요한 사항</h2>',
            '<p>아래 항목을 확인한 뒤 최종 결정을 기록하십시오.</p>',
            f'<ul class="attention-list">{entries}</ul>',
            "</section>",
        )
    )


__all__ = [
    "render_additional_review",
    "render_review_item_navigation",
    "render_status_band",
    "render_summary",
]
