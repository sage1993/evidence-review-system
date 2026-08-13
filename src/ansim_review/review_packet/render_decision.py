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
    packet_hash = _text(decision.get("packet_sha256"))
    return "".join(
        (
            '<section id="decision-form" aria-labelledby="decision-heading">',
            '<span class="section-kicker">4. 검토자 의견</span>',
            '<div class="decision-heading"><div><h2 id="decision-heading">최종 결정</h2>',
            '<p>결정과 검토 의견만 입력하십시오. 검토자 ID·시각·패킷 해시는 ',
            '보호 세션 또는 저장 시 자동 결합됩니다.</p></div>',
            '<span class="authority-badge">검토자 확정</span></div>',
            '<form action="./decision" method="post">',
            f'<input type="hidden" name="packet_sha256" value="{packet_hash}">',
            '<fieldset class="decision-choices"><legend>결정 선택</legend>',
            option_html
            or (
                '<label class="decision-option"><input type="radio" name="decision" '
                'value="" required disabled><span><strong>허용된 결정 값 없음</strong>'
                "</span></label>"
            ),
            "</fieldset>",
            '<label class="decision-notes">검토 의견<textarea name="notes" rows="4" required ',
            'placeholder="판단 근거 또는 후속 확인 사항을 기록합니다."></textarea></label>',
            '<p class="reviewer-session" data-reviewer-session>',
            '보호 세션에서는 검토자 ID를 자동 사용합니다. 보관 HTML에서는 ',
            '결정 JSON 다운로드 시 한 번 확인합니다.</p>',
            '<div class="decision-actions"><button class="primary-action" ',
            'type="submit">결정 저장</button>',
            '<button type="button" data-download-decision>결정 JSON 다운로드</button></div>',
            '<p class="decision-storage-note">HTML 파일 저장은 결정 기록 저장이 아닙니다. ',
            '보관 HTML에서는 결정 JSON을 다운로드한 뒤 승인된 import 경로로 반영하십시오.</p>',
            '<p class="form-status" aria-live="polite"></p>',
            "</form></section>",
        )
    )


__all__ = ["render_decision_form"]
