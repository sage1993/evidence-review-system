from __future__ import annotations

import importlib

import pytest

from evidence_review.contracts.question_plan import (
    QUESTION_PLAN_FORMAT,
    QuestionPlan,
    decode_question_plan,
)
from evidence_review.question_planning import question_plan_sha256

QUESTION = "제12조 기준에서 300m 이격된 1,500㎡ 부지의 검토 가능 여부를 확인해줘."


def _adapters_module():
    try:
        return importlib.import_module("evidence_review.review_matter.scope_adapters")
    except ModuleNotFoundError as error:
        pytest.fail(f"REVIEW_SCOPE_ADAPTERS_MISSING: {error}")


def _plan() -> QuestionPlan:
    return decode_question_plan(
        {
            "format": QUESTION_PLAN_FORMAT,
            "version": 2,
            "original_question": QUESTION,
            "facts": [
                {"id": "F1", "text": "경계에서 300m 이격되어 있다.", "polarity": "positive"},
                {"id": "F2", "text": "부지 면적은 1,500㎡이다.", "polarity": "positive"},
            ],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "300m 이격 기준을 충족하는가?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
            ],
            "legal_anchors": [{"text": "제12조", "source": "user"}],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "300m 이격 제12조 기준",
                    "kind": "legal_anchor",
                    "source": "planner",
                    "role": "rule",
                }
            ],
        },
        QUESTION,
    )


def test_question_plan_adapter_preserves_scope_and_provenance() -> None:
    plan = _plan()

    scope = _adapters_module().review_scope_from_question_plan(plan)

    assert scope.question == plan.original_question
    assert scope.facts == plan.facts
    assert scope.assumptions == plan.assumptions
    assert scope.issues == plan.issues
    assert scope.legal_anchors == plan.legal_anchors
    assert scope.search_requests == plan.search_requests
    assert scope.origin == "PLANNER"
    assert scope.question_plan_sha256 == question_plan_sha256(plan)


def test_explicit_adapter_has_same_semantics_without_planner_lineage() -> None:
    plan = _plan()

    scope = _adapters_module().review_scope_from_explicit_input(
        question=plan.original_question,
        facts=plan.facts,
        assumptions=plan.assumptions,
        issues=plan.issues,
        legal_anchors=plan.legal_anchors,
        search_requests=plan.search_requests,
    )

    assert scope.question == plan.original_question
    assert scope.facts == plan.facts
    assert scope.issues == plan.issues
    assert scope.search_requests == plan.search_requests
    assert scope.origin == "EXPLICIT_USER"
    assert scope.question_plan_sha256 is None


@pytest.mark.parametrize("value", [object(), None, {"issues": []}])
def test_adapters_reject_unvalidated_question_plan_input(value: object) -> None:
    with pytest.raises(ValueError):
        _adapters_module().review_scope_from_question_plan(value)


def test_planner_legal_anchor_remains_hypothesis_not_evidence() -> None:
    scope = _adapters_module().review_scope_from_question_plan(_plan())

    assert all(anchor.source in {"user", "planner"} for anchor in scope.legal_anchors)
    assert not hasattr(scope, "evidence")
    assert not hasattr(scope, "final_status")
