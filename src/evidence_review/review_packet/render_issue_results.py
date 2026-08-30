"""Read-only presentation of deterministic issue results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import cast

from evidence_review.review_packet.presentation import (
    issue_result_gap_items,
    localized_status,
)


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return ()
    return cast(Sequence[object], value)


def _id_list(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value))


def render_issue_results(model: Mapping[str, object]) -> str:
    """Render issue status and lineage fields without recalculating them."""
    raw_results = _sequence(model.get("issue_results"))
    if not raw_results:
        return ""

    cards: list[str] = []
    gap_items = issue_result_gap_items(model)
    for raw_result in raw_results:
        result = _mapping(raw_result)
        issue_id = str(result.get("issue_id", ""))
        status = str(result.get("status", ""))
        covered = _id_list(result.get("covered_facet_ids", []))
        missing = _id_list(result.get("missing_facet_ids", []))
        comparisons = _id_list(result.get("comparison_ids", []))
        gaps = _id_list(result.get("gap_codes", []))
        issue_gaps = tuple(item for item in gap_items if item.startswith(f"{issue_id}:"))
        gap_html = "".join(f"<li>{_text(item)}</li>" for item in issue_gaps)
        detail_html = "".join(
            (
                '<details class="issue-result-audit">',
                "<summary>근거 연결 정보</summary>",
                '<dl class="issue-lineage">',
                f"<div><dt>확인된 기준</dt><dd>{_text(', '.join(covered) or '없음')}</dd></div>",
                f"<div><dt>미확인 기준</dt><dd>{_text(', '.join(missing) or '없음')}</dd></div>",
                f"<div><dt>비교 결과</dt><dd>{_text(', '.join(comparisons) or '없음')}</dd></div>",
                f"<div><dt>추가 확인 사유</dt><dd>{_text(', '.join(gaps) or '없음')}</dd></div>",
                "</dl></details>",
            )
        )
        cards.append(
            "".join(
                (
                    f'<article class="issue-result" data-issue-id="{_text(issue_id)}" ',
                    f'data-issue-status="{_text(status)}">',
                    '<header class="issue-result-heading">',
                    f'<h3>{_text(issue_id)}</h3>',
                    f'<span class="status-pill">{_text(localized_status(status))}</span>',
                    "</header>",
                    '<p class="issue-result-facts">',
                    f"확인된 기준 {_text(len(covered))}건 · ",
                    f"미확인 기준 {_text(len(missing))}건 · ",
                    f"비교 결과 {_text(len(comparisons))}건</p>",
                    f'<ul class="issue-gap-list">{gap_html}</ul>' if gap_html else "",
                    detail_html,
                    "</article>",
                )
            )
        )

    return "".join(
        (
            '<section id="review-issue-results" class="issue-results" ',
            'data-review-section="issue-results" aria-labelledby="issue-results-heading">',
            '<div class="panel-heading"><div><span class="section-kicker">쟁점별 결과</span>',
            '<h2 id="issue-results-heading">전체 검토 쟁점</h2></div></div>',
            f'<div class="issue-result-list">{"".join(cards)}</div>',
            "</section>",
        )
    )


__all__ = ["render_issue_results"]
