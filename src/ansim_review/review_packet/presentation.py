"""Non-developer presentation policy for the Review Workspace."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

_STATUS_LABELS = {
    "ABSTAIN": "추가 자료 필요",
    "READY_FOR_HUMAN_REVIEW": "검토 준비 완료",
    "REVIEW_COMPLETED": "검토 완료",
    "INDETERMINATE": "판단 보류",
    "COMPLETE": "근거 연결 완료",
    "MISSING_REQUIRED_INPUT": "필요한 자료가 부족합니다",
    "SATISFIED": "충족",
    "NOT_SATISFIED": "미충족",
    "CONDITIONAL": "조건부",
    "ADDITIONAL_REVIEW_REQUIRED": "추가 자료 필요",
}

_ISSUE_LABELS = {
    "MISSING_REQUIRED_INPUT": "필요한 입력 자료가 없습니다.",
    "SOURCE_CONFLICT": "서로 다른 출처의 내용이 일치하지 않습니다.",
    "UNRESOLVED_CONFLICT": "해결되지 않은 근거 충돌이 있습니다.",
    "LOW_CONFIDENCE": "근거 신뢰도를 추가로 확인해야 합니다.",
    "TRACK_B_REJECTED": "교차 검증에서 추가 확인이 필요하다고 판단했습니다.",
}

_NO_ANSWER_FALLBACK = "질문에 대한 결론이 제공되지 않았습니다."
_EVIDENCE_TYPE_LABELS = {
    "clause": "조항 근거",
    "text": "본문 근거",
    "table": "표 근거",
    "visual": "시각 근거",
}


def evidence_type_label(value: object) -> str | None:
    """Return a reviewer label only for canonical evidence types."""
    if not isinstance(value, str):
        return None
    return _EVIDENCE_TYPE_LABELS.get(value)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return ()
    return cast(Sequence[object], value)


def localized_status(value: object) -> str:
    raw = "" if value is None else str(value)
    return _STATUS_LABELS.get(raw, raw.replace("_", " ") if raw else "상태 확인 필요")


def conclusion_text(model: Mapping[str, object]) -> str:
    """Return only an explicit reviewer-facing answer, never a workflow-status paraphrase."""
    value = model.get("answer_summary")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return _NO_ANSWER_FALLBACK


def _human_issue(value: object) -> str:
    raw = str(value)
    return _ISSUE_LABELS.get(raw, raw.replace("_", " "))


def additional_review_items(model: Mapping[str, object]) -> tuple[str, ...]:
    """Return only present missing/conflict/exception/abstention items."""
    values: list[str] = []

    for item in _sequence(model.get("missing_inputs")):
        human = _human_issue(item)
        if human and human not in values:
            values.append(human)

    for rule_value in _sequence(model.get("rules")):
        rule = _mapping(rule_value)
        for item in _sequence(rule.get("missing_inputs")):
            human = _human_issue(item)
            if human and human not in values:
                values.append(human)

    for source in (
        _sequence(model.get("exceptions")),
        _sequence(model.get("conflicts")),
        _sequence(model.get("abstention_reasons")),
    ):
        for item in source:
            human = _human_issue(item)
            if human and human not in values:
                values.append(human)
    return tuple(values)


def has_rules_or_calculations(model: Mapping[str, object]) -> bool:
    return bool(_sequence(model.get("rules")) or _sequence(model.get("calculations")))


__all__ = [
    "additional_review_items",
    "conclusion_text",
    "evidence_type_label",
    "has_rules_or_calculations",
    "localized_status",
]
