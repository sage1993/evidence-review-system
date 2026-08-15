from __future__ import annotations

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.question_planning import query_request_from_plan
from evidence_review.retrieval.bundle import _normalize_request


def _rule_plan():
    question = "역 승강장 경계에서 300m 떨어진 1,500㎡ 부지에서 사업을 추진할 수 있어?"
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [
                {
                    "id": "F1",
                    "text": "역 승강장 경계에서 300m 떨어져 있다.",
                    "polarity": "positive",
                },
                {"id": "F2", "text": "부지 면적은 1,500㎡이다.", "polarity": "positive"},
            ],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "역세권 거리 기준을 충족하는가?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "역세권 승강장 경계 거리 기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                }
            ],
        },
        question,
    )


def test_original_question_is_preserved_in_plan_but_not_used_as_retrieval_primary() -> None:
    plan = _rule_plan()

    request = query_request_from_plan(plan)
    normalized, *_ = _normalize_request(request)

    assert plan.original_question == (
        "역 승강장 경계에서 300m 떨어진 1,500㎡ 부지에서 사업을 추진할 수 있어?"
    )
    assert request["question"] == "역세권 승강장 경계 거리 기준"
    assert normalized.primary == "역세권 승강장 경계 거리 기준"
    assert "300m" not in normalized.primary
    assert "1,500㎡" not in normalized.primary
    assert all(term.text != plan.original_question for term in normalized.terms)
    primary_term = next(term for term in normalized.terms if term.text == normalized.primary)
    assert primary_term.origin == "llm"
    assert primary_term.search_request_ids == ("S1",)
    assert primary_term.issue_ids == ("I1",)


def test_rule_request_is_preferred_for_primary_over_supporting_fact_request() -> None:
    question = "사업대상지의 외부 사실과 적용 기준을 확인해줘"
    plan = decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "외부 사실과 기준은 무엇인가?",
                    "depends_on": [],
                    "required_evidence_roles": ["supporting_fact", "rule"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "대상지 외부 사실 확인",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "supporting_fact",
                },
                {
                    "id": "S2",
                    "issue_ids": ["I1"],
                    "text": "사업대상지 적용 기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
            ],
        },
        question,
    )

    request = query_request_from_plan(plan)

    assert request["question"] == "사업대상지 적용 기준"


def test_supporting_fact_only_plan_uses_first_search_request_as_primary() -> None:
    question = "대상지의 지정 현황을 확인해줘"
    plan = decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "대상지 지정 현황은 무엇인가?",
                    "depends_on": [],
                    "required_evidence_roles": ["supporting_fact"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "대상지 지정 현황",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "supporting_fact",
                }
            ],
        },
        question,
    )

    request = query_request_from_plan(plan)

    assert request["question"] == "대상지 지정 현황"


def test_explicit_user_expansion_may_still_contain_user_fact_value() -> None:
    request = query_request_from_plan(_rule_plan(), user_expansions=("300m",))
    normalized, *_ = _normalize_request(request)

    user_term = next(term for term in normalized.terms if term.text == "300m")
    assert user_term.origin == "user"
