from __future__ import annotations

import copy

import pytest

from evidence_review.llm_layer.question_planner import (
    build_question_planner_bundle,
    validate_question_planner_output,
)
from evidence_review.question_planning import (
    bind_question_plan_to_review_request,
    prepare_question_planner_handoff,
    question_plan_sha256,
)

QUESTION = "에어컨 등 가전제품 설치기준 알려줘"


def _plan() -> dict[str, object]:
    return {
        "format": "evidence-review/question-plan",
        "version": 3,
        "original_question": QUESTION,
        "facts": [],
        "assumptions": [],
        "issues": [
            {
                "id": "I1",
                "question": "설치기준은 무엇인가",
                "depends_on": [],
                "required_evidence_roles": ["rule"],
                "required_facet_ids": ["installation_criteria"],
            }
        ],
        "legal_anchors": [],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "에어컨 설치기준",
                "kind": "phrase",
                "source": "planner",
                "role": "rule",
            }
        ],
    }


def test_build_question_planner_bundle_contains_only_question_and_contract_metadata() -> None:
    bundle = build_question_planner_bundle("  에어컨 등   가전제품 설치기준 알려줘  ")

    assert bundle == {
        "format": "evidence-review/question-planner-bundle",
        "version": 1,
        "original_question": QUESTION,
        "raw_user_question": "  에어컨 등   가전제품 설치기준 알려줘  ",
        "normalized_question": QUESTION,
        "question_plan_format": "evidence-review/question-plan",
        "question_plan_version": 3,
    }
    assert "evidence" not in bundle
    assert "answer" not in bundle


def test_build_question_planner_bundle_preserves_raw_question_provenance() -> None:
    bundle = build_question_planner_bundle("  안심주택 운영기준에서\n질문  ")

    assert bundle["raw_user_question"] == "  안심주택 운영기준에서\n질문  "
    assert bundle["normalized_question"] == "안심주택 운영기준에서 질문"


def test_planner_handoff_identity_preserves_raw_whitespace(tmp_path) -> None:
    compact = prepare_question_planner_handoff(
        tmp_path, "안심주택 운영기준에서 조건 알려줘"
    )
    spaced = prepare_question_planner_handoff(
        tmp_path, "안심주택 운영기준에서   조건 알려줘"
    )

    assert compact.planning_directory != spaced.planning_directory
    assert compact.bundle_path.read_bytes() != spaced.bundle_path.read_bytes()
    assert (
        compact.bundle_path.read_text(encoding="utf-8")
        != spaced.bundle_path.read_text(encoding="utf-8")
    )


def test_planner_handoff_identity_preserves_raw_line_break(tmp_path) -> None:
    inline = prepare_question_planner_handoff(
        tmp_path, "안심주택 운영기준에서 조건 알려줘"
    )
    multiline = prepare_question_planner_handoff(
        tmp_path, "안심주택 운영기준에서\n조건 알려줘"
    )

    assert inline.planning_directory != multiline.planning_directory
    assert inline.bundle_path.read_bytes() != multiline.bundle_path.read_bytes()


def test_question_provenance_is_bound_into_review_request_inputs() -> None:
    raw = _plan()
    raw["raw_user_question"] = QUESTION
    raw["normalized_question"] = QUESTION
    raw["document_context"] = [{"text": "안심주택 운영기준", "source": "document"}]
    raw["planner_inference"] = [{"text": "범위별 기준 검색", "source": "planner"}]
    plan = validate_question_planner_output(raw, QUESTION)

    bound = bind_question_plan_to_review_request(
        {"question": QUESTION, "inputs": {}},
        plan,
    )

    assert bound["inputs"]["question_provenance"] == {
        "raw_user_question": QUESTION,
        "normalized_question": QUESTION,
        "document_context": [{"text": "안심주택 운영기준", "source": "document"}],
        "planner_inference": [{"text": "범위별 기준 검색", "source": "planner"}],
    }


def test_validate_question_planner_output_fails_closed() -> None:
    plan = validate_question_planner_output(_plan(), QUESTION)
    assert plan.original_question == QUESTION

    raw = _plan()
    raw["answer"] = "forbidden"
    with pytest.raises(ValueError, match="unknown fields"):
        validate_question_planner_output(raw, QUESTION)


def test_current_external_planner_rejects_legacy_v1_output() -> None:
    raw = copy.deepcopy(_plan())
    raw["version"] = 1
    issues = raw["issues"]
    requests = raw["search_requests"]
    assert isinstance(issues, list)
    assert isinstance(requests, list)
    issues[0].pop("required_evidence_roles")
    requests[0].pop("role")

    with pytest.raises(ValueError, match="must use question plan version 3"):
        validate_question_planner_output(raw, QUESTION)


def test_question_plan_sha256_is_stable_for_canonical_plan() -> None:
    left = validate_question_planner_output(_plan(), QUESTION)
    right = validate_question_planner_output(_plan(), QUESTION)

    assert question_plan_sha256(left) == question_plan_sha256(right)
    assert len(question_plan_sha256(left)) == 64
