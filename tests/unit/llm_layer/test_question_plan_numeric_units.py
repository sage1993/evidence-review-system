from __future__ import annotations

import pytest

from evidence_review.contracts.question_plan import decode_question_plan


def _plan(question: str, facts: list[dict[str, str]]) -> dict[str, object]:
    return {
        "format": "evidence-review/question-plan",
        "version": 1,
        "original_question": question,
        "facts": facts,
        "assumptions": [],
        "issues": [{"id": "I1", "question": "부지 기준은 무엇인가", "depends_on": []}],
        "legal_anchors": [],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "부지 기준",
                "kind": "phrase",
                "source": "planner",
            }
        ],
    }


def test_question_plan_rejects_numeric_unit_substitution() -> None:
    question = "역 경계에서 300m 떨어진 1,500㎡ 부지를 검토해줘"
    raw = _plan(
        question,
        [
            {"id": "F1", "text": "역 경계에서 300㎡ 떨어져 있다", "polarity": "positive"},
            {"id": "F2", "text": "부지 면적은 1500㎡이다", "polarity": "positive"},
        ],
    )

    with pytest.raises(ValueError, match="numeric literal"):
        decode_question_plan(raw, question)


def test_question_plan_accepts_comma_normalization_with_same_units() -> None:
    question = "역 경계에서 300m 떨어진 1,500㎡ 부지를 검토해줘"
    raw = _plan(
        question,
        [
            {"id": "F1", "text": "역 경계에서 300m 떨어져 있다", "polarity": "positive"},
            {"id": "F2", "text": "부지 면적은 1500㎡이다", "polarity": "positive"},
        ],
    )

    plan = decode_question_plan(raw, question)

    assert [item.text for item in plan.facts] == [
        "역 경계에서 300m 떨어져 있다",
        "부지 면적은 1500㎡이다",
    ]


def test_question_plan_preserves_percent_semantics() -> None:
    question = "전체 부지의 45%가 범위 안에 있는 경우를 검토해줘"
    raw = _plan(
        question,
        [{"id": "F1", "text": "전체 부지의 45%가 범위 안에 있다", "polarity": "positive"}],
    )

    assert decode_question_plan(raw, question).facts[0].text.startswith("전체 부지의 45%")
