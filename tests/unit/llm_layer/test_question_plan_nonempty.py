from __future__ import annotations

import pytest

from evidence_review.contracts.question_plan import decode_question_plan

QUESTION = "에어컨 등 가전제품 설치기준 알려줘"


def _base_plan() -> dict[str, object]:
    return {
        "format": "evidence-review/question-plan",
        "version": 1,
        "original_question": QUESTION,
        "facts": [],
        "assumptions": [],
        "issues": [{"id": "I1", "question": "설치기준은 무엇인가", "depends_on": []}],
        "legal_anchors": [],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "에어컨 설치기준",
                "kind": "phrase",
                "source": "planner",
            }
        ],
    }


def test_question_plan_requires_at_least_one_issue() -> None:
    plan = _base_plan()
    plan["issues"] = []
    plan["search_requests"] = []

    with pytest.raises(ValueError, match="issues must not be empty"):
        decode_question_plan(plan, QUESTION)


def test_question_plan_requires_at_least_one_search_request() -> None:
    plan = _base_plan()
    plan["search_requests"] = []

    with pytest.raises(ValueError, match="search_requests must not be empty"):
        decode_question_plan(plan, QUESTION)
