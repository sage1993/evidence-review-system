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
    """Render the existing decision envelope; #91 simplifies the input contract."""
    decision = _mapping(model.get("decision", {}), "decision")
    options = _sequence(decision.get("allowed_values", []), "decision.allowed_values")
    labels = {
        "SATISFIED": "내용 확인 완료",
        "NOT_SATISFIED": "내용에 오류 있음",
        "CONDITIONAL": "조건부 확인",
        "ADDITIONAL_REVIEW_REQUIRED": "추가 자료 필요",
    }
    option_html = "".join(
        '<label class="decision-option"><input type="radio" name="decision" '
        f'value="{_text(option)}" required><span><strong>'
        f'{_text(labels.get(str(option), str(option)))}</strong></span></label>'
        for option in options
    )
    return "".join(
        (
            '<section id="decision-form" aria-labelledby="decision-heading">',
            '<span class="section-kicker">4. 검토자 의견</span>',
            '<div class="decision-heading"><div><h2 id="decision-heading">최종 결정</h2>',
            '<p>근거를 확인한 뒤 검토자의 판단을 기록합니다.</p></div>',
            '<span class="authority-badge">검토자 확정</span></div>',
            '<form action="./decision" method="post">',
            '<fieldset class="decision-choices"><legend>결정 선택</legend>',
            option_html
            or (
                '<label class="decision-option"><input type="radio" name="decision" '
                'value="" required disabled><span><strong>허용된 결정 값 없음</strong>'
                "</span></label>"
            ),
            "</fieldset>",
            '<div class="decision-fields">',
            '<label>검토자 ID<input name="reviewer_id" autocomplete="name" required></label>',
            '<label>검토 시각<input name="reviewed_at" '
            'placeholder="ISO-8601 시간대 포함" required></label>',
            '<label class="packet-hash">패킷 SHA-256<input name="packet_sha256" '
            f'value="{_text(decision.get("packet_sha256"))}" readonly required></label>',
            "</div>",
            '<label class="decision-notes">검토 의견<textarea name="notes" rows="4" required '
            'placeholder="판단 근거 또는 후속 확인 사항을 기록합니다."></textarea></label>',
            '<div class="decision-actions"><button class="primary-action" '
            'type="submit">결정 저장</button>',
            '<button type="button" data-download-decision>결정 JSON 다운로드</button></div>',
            '<p class="form-status" aria-live="polite"></p>',
            "</form></section>",
        )
    )


__all__ = ["render_decision_form"]
