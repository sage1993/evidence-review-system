from __future__ import annotations

import pytest

from evidence_review.llm_layer.question_planner import (
    build_question_planner_bundle,
    validate_question_planner_output,
)
from evidence_review.question_planning import question_plan_sha256

QUESTION = "에어컨 등 가전제품 설치기준 알려줘"


def _plan() -> dict[str, object]:
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


def test_build_question_planner_bundle_contains_only_question_and_contract_metadata() -> None:
    bundle = build_question_planner_bundle("  에어컨 등   가전제품 설치기준 알려줘  ")

    assert bundle == {
        "format": "evidence-review/question-planner-bundle",
        "version": 1,
        "original_question": QUESTION,
        "question_plan_format": "evidence-review/question-plan",
        "question_plan_version": 1,
    }
    assert "evidence" not in bundle
    assert "answer" not in bundle


def test_validate_question_planner_output_fails_closed() -> None:
    plan = validate_question_planner_output(_plan(), QUESTION)
    assert plan.original_question == QUESTION

    raw = _plan()
    raw["answer"] = "forbidden"
    with pytest.raises(ValueError, match="unknown fields"):
        validate_question_planner_output(raw, QUESTION)


def test_question_plan_sha256_is_stable_for_canonical_plan() -> None:
    left = validate_question_planner_output(_plan(), QUESTION)
    right = validate_question_planner_output(_plan(), QUESTION)

    assert question_plan_sha256(left) == question_plan_sha256(right)
    assert len(question_plan_sha256(left)) == 64
