"""Human decision panel rendering."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import cast


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def render_decision_form(model: Mapping[str, object]) -> str:
    """Render only the human decision and notes as ordinary user inputs."""
    decision = _mapping(model.get("decision", {}), "decision")
    options = _sequence(decision.get("allowed_values", []), "decision.allowed_values")
    labels = {
        "SATISFIED": "검토 결과에 동의",
        "NOT_SATISFIED": "검토 결과에 오류 있음",
        "CONDITIONAL": "조건 충족 시 동의",
        "ADDITIONAL_REVIEW_REQUIRED": "추가 자료 검토 필요",
    }
    option_html = "".join(
        '<label class="decision-option"><input type="radio" name="decision" '
        f'value="{_text(option)}" required><span><strong>'
        f'{_text(labels.get(str(option), str(option)))}</strong></span></label>'
        for option in options
    )
    packet_hash = _text(decision.get("packet_sha256"))
    return "".join(
        (
            '<section id="decision-form" aria-labelledby="decision-heading">',
            '<span class="section-kicker">검토자 의견</span>',
            '<div class="decision-heading"><div><h2 id="decision-heading">최종 결정</h2>',
            '<p data-protected-only hidden>검토 결과를 선택하고 필요한 의견을 입력하십시오.</p>',
            '<p data-archive-only>검토 결과를 선택하고 필요한 의견을 입력하십시오. ',
            '보관 HTML에서는 결정 JSON을 별도로 저장할 수 있습니다.</p></div>',
            '<span class="authority-badge">검토자 확정</span></div>',
            '<form action="./decision" method="post" novalidate>',
            f'<input type="hidden" name="packet_sha256" value="{packet_hash}">',
            '<fieldset class="decision-choices"><legend>결정 선택</legend>',
            option_html
            or (
                '<label class="decision-option"><input type="radio" name="decision" '
                'value="" required disabled><span><strong>허용된 결정 값 없음</strong>'
                '</span></label>'
            ),
            '</fieldset>',
            '<label class="decision-notes" for="review-notes">검토 의견</label>',
            '<textarea id="review-notes" name="notes" rows="4" ',
            'aria-describedby="notes-help notes-error" ',
            'placeholder="오류, 조건 또는 추가 확인이 필요한 내용을 기록합니다."></textarea>',
            '<p id="notes-help" class="form-help">검토 결과에 동의하는 경우 의견은 선택사항입니다. ',
            '그 외 판정에서는 의견을 입력해야 합니다.</p>',
            '<p id="notes-error" class="field-error" hidden>이 판정에는 검토 의견이 필요합니다.</p>',
            '<p class="reviewer-session" data-reviewer-session></p>',
            '<div class="decision-actions"><button class="primary-action" ',
            'type="submit">결정 저장</button>',
            '<button type="button" data-download-decision data-archive-only>결정 JSON 다운로드</button></div>',
            '<p class="decision-storage-note" data-archive-only>보관 HTML의 결정 JSON은 ',
            '승인된 import 경로를 통해 정식 결정 기록으로 반영합니다.</p>',
            '<p class="form-status" aria-live="polite"></p>',
            '</form></section>',
        )
    )


__all__ = ["render_decision_form"]
