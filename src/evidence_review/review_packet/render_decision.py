"""Human decision panel rendering."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import cast

from evidence_review.review_packet.icons import icon_svg


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


def render_decision_form(model: Mapping[str, object], *, initially_hidden: bool = False) -> str:
    decision = _mapping(model.get("decision", {}), "decision")
    options = _sequence(decision.get("allowed_values", []), "decision.allowed_values")
    labels = {
        "SATISFIED": "검토 결과에 동의",
        "NOT_SATISFIED": "검토 결과에 오류 있음",
        "CONDITIONAL": "조건 충족 시 동의",
        "ADDITIONAL_REVIEW_REQUIRED": "추가 자료 검토 필요",
    }
    recorded_decision = decision.get("human_decision", model.get("human_decision"))
    recorded_label = labels.get(str(recorded_decision), str(recorded_decision))
    option_html = "".join(
        '<label class="decision-option"><input type="radio" name="decision" '
        f'value="{_text(option)}" required><strong>'
        f'{_text(labels.get(str(option), str(option)))}</strong></label>'
        for option in options
    )
    return "".join(
        (
            '<section id="decision-form"',
            ' aria-hidden="true"' if initially_hidden else "",
            ' aria-labelledby="decision-heading">',
            '<p data-protected-only hidden>검토 결과를 선택하고 필요한 의견을 입력하십시오.</p>',
            '<p data-archive-only>검토 결과를 선택하고 필요한 의견을 입력하십시오.</p>',
            '<span class="visually-hidden">최종 결정</span>',
            '<div class="decision-panel-heading"><h2 id="decision-heading">검토자 의견</h2></div>',
            '<div class="persisted-decision" data-persisted-decision hidden>',
            '<h3>기록된 사람의 결정</h3>',
            '<dl>',
            '<div><dt>검토자</dt><dd data-persisted-reviewer></dd></div>',
            '<div><dt>검토 시각</dt><dd data-persisted-reviewed-at></dd></div>',
            '<div><dt>결정</dt><dd data-persisted-decision-value></dd></div>',
            '<div><dt>검토 의견</dt><dd data-persisted-notes></dd></div>',
            '</dl>',
            '<button type="button" class="secondary-action" data-add-decision ',
            'data-protected-only hidden>추가 결정 기록</button>',
            '<p class="decision-storage-note">',
            icon_svg("lock", size=14),
            ' 기존 기록은 수정하지 않고 새 검토 기록을 추가합니다.</p>',
            '</div>',
            (
                '<p class="recorded-human-decision">기록된 사람의 결정: '
                f'{_text(recorded_label)}</p>'
                if recorded_decision is not None
                else ""
            ),
            '<form action="./decision" method="post">',
            '<div data-decision-editor>',
            '<fieldset class="decision-choices"><legend>판정</legend>',
            option_html or '<p class="empty-state">허용된 결정 값이 없습니다.</p>',
            '</fieldset>',
            '<label class="decision-reviewer">검토자 ID <span class="notes-optional">(필수)</span>',
            '<input id="decision-reviewer-id" name="reviewer_id" type="text" required ',
            'maxlength="128" pattern="[A-Za-z0-9][A-Za-z0-9._-]{0,127}" ',
            'autocomplete="username" spellcheck="false" ',
            'aria-describedby="reviewer-id-help reviewer-id-error" ',
            'placeholder="예: reviewer-01">',
            '<span id="reviewer-id-help" class="visually-hidden">',
            '영문·숫자로 시작하며 영문·숫자·점·밑줄·하이픈만 사용할 수 있습니다.</span>',
            '<span id="reviewer-id-error" class="visually-hidden"></span>',
            '</label>',
            '<label class="decision-notes">검토 의견 <span class="notes-optional">(선택)</span>',
            '<textarea id="decision-notes" name="notes" rows="4" maxlength="1000" ',
            'data-notes-required-for="NOT_SATISFIED CONDITIONAL ADDITIONAL_REVIEW_REQUIRED" ',
            'aria-describedby="decision-notes-error notes-help notes-error" aria-invalid="false" ',
            'placeholder="검토 의견을 입력하세요.\n(선택 사항)"></textarea>',
            '<span id="review-notes" class="visually-hidden" aria-hidden="true"></span>',
            '<p id="notes-help" class="visually-hidden">notes help</p>',
            '<p id="notes-error" class="visually-hidden"></p>',
            '<span class="decision-note-footer"><span></span><span data-notes-count>',
            '0 / 1,000</span></span>',
            '</label>',
            '<p id="decision-notes-error" class="field-error" role="alert" aria-live="polite"></p>',
            '<p class="reviewer-session visually-hidden" data-reviewer-session></p>',
            '<div class="decision-actions"><button class="primary-action" data-protected-only ',
            'type="submit">결정 저장</button>',
            '<button type="button" class="secondary-action" data-download-decision ',
            'data-archive-only hidden>결정 JSON 다운로드</button></div>',
            '<p class="decision-storage-note">',
            icon_svg("lock", size=14),
            ' 저장 시 검토 기록이 추가되며, 이후 수정은 불가능합니다.</p>',
            '</div>',
            '<p class="form-status" aria-live="polite"></p>',
            '</form></section>',
        )
    )


__all__ = ["render_decision_form"]
