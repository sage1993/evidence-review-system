from __future__ import annotations

import pytest

from evidence_review.contracts.question_plan import decode_question_plan


def _plan(question: str, legal_anchors: list[dict[str, str]]) -> dict[str, object]:
    return {
        "format": "evidence-review/question-plan",
        "version": 1,
        "original_question": question,
        "facts": [],
        "assumptions": [],
        "issues": [{"id": "I1", "question": "적용 기준은 무엇인가", "depends_on": []}],
        "legal_anchors": legal_anchors,
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "적용 기준",
                "kind": "phrase",
                "source": "planner",
            }
        ],
    }


def test_question_plan_rejects_dropped_explicit_article_citation() -> None:
    question = "건축법 제51조제1항제1호의 적용 여부를 검토해줘"
    raw = _plan(question, [])

    with pytest.raises(ValueError, match="user legal citation"):
        decode_question_plan(raw, question)


def test_question_plan_accepts_explicit_article_citation_as_user_anchor() -> None:
    question = "건축법 제51조제1항제1호의 적용 여부를 검토해줘"
    raw = _plan(
        question,
        [{"text": "제51조제1항제1호", "source": "user"}],
    )

    plan = decode_question_plan(raw, question)

    assert plan.legal_anchors[0].text == "제51조제1항제1호"
    assert plan.legal_anchors[0].source == "user"


def test_question_plan_rejects_dropped_explicit_appendix_citation() -> None:
    question = "서울시 조례 별표 2의 주차기준을 검토해줘"
    raw = _plan(question, [])

    with pytest.raises(ValueError, match="user legal citation"):
        decode_question_plan(raw, question)


def test_question_plan_accepts_appendix_spacing_normalization() -> None:
    question = "서울시 조례 별표 2의 주차기준을 검토해줘"
    raw = _plan(
        question,
        [{"text": "별표 2", "source": "user"}],
    )

    assert decode_question_plan(raw, question).legal_anchors[0].source == "user"


def test_non_legal_prefix_like_second_class_zone_is_not_misclassified() -> None:
    question = "제2종일반주거지역의 용적률 기준을 검토해줘"
    raw = _plan(question, [])
    raw["facts"] = [
        {"id": "F1", "text": "제2종일반주거지역이다", "polarity": "positive"}
    ]

    assert decode_question_plan(raw, question).facts[0].text == "제2종일반주거지역이다"
