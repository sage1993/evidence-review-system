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
    """Return one concise reviewer-facing conclusion without inventing facts."""
    raw_status = str(model.get("status", ""))
    summary = _mapping(model.get("summary"))
    citation_count = summary.get("citation_count", 0)
    missing_count = summary.get("missing_input_count", 0)
    conflict_count = summary.get("conflict_count", 0)
    exception_count = summary.get("exception_count", 0)
    if raw_status == "ABSTAIN":
        return "현재 근거만으로 확정하기 어려워 추가 자료 확인이 필요합니다."
    if raw_status == "READY_FOR_HUMAN_REVIEW":
        if any(
            value not in (0, None, "0")
            for value in (missing_count, conflict_count, exception_count)
        ):
            return "검토 자료가 준비되었으나 일부 항목은 추가 확인이 필요합니다."
        return f"근거 {citation_count}건이 연결되어 최종 검토가 가능한 상태입니다."
    if raw_status == "INDETERMINATE":
        return "현재 자료로는 판단을 확정할 수 없습니다."
    if raw_status == "MISSING_REQUIRED_INPUT":
        return "판단에 필요한 입력 자료가 부족합니다."
    if raw_status == "COMPLETE":
        return "질문과 근거의 연결이 완료되었습니다."
    return f"현재 검토 상태는 ‘{localized_status(raw_status)}’입니다."


def _human_issue(value: object) -> str:
    raw = str(value)
    return _ISSUE_LABELS.get(raw, raw.replace("_", " "))


def additional_review_items(model: Mapping[str, object]) -> tuple[str, ...]:
    """Return only present missing/conflict/exception/abstention items."""
    values: list[str] = []

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
    "has_rules_or_calculations",
    "localized_status",
]
