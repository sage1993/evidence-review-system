from __future__ import annotations

import copy

import pytest

from evidence_review.contracts.question_plan import (
    QUESTION_PLAN_FORMAT,
    QUESTION_PLAN_VERSION,
    decode_question_plan,
    question_plan_document,
)

QUESTION = "역 승강장 경계에서 300m 떨어진 1,500㎡ 부지의 사업 가능 여부를 검토해줘."


def _v2_payload() -> dict[str, object]:
    return {
        "format": QUESTION_PLAN_FORMAT,
        "version": 2,
        "original_question": QUESTION,
        "facts": [
            {"id": "F1", "text": "역 승강장 경계에서 300m 떨어져 있다.", "polarity": "positive"},
            {"id": "F2", "text": "부지 면적은 1,500㎡이다.", "polarity": "positive"},
        ],
        "assumptions": [],
        "issues": [
            {
                "id": "I1",
                "question": "역세권 거리 기준을 충족하는가?",
                "depends_on": [],
                "required_evidence_roles": ["rule"],
            },
            {
                "id": "I2",
                "question": "해당 부지에 외부 사실확인이 필요한가?",
                "depends_on": [],
                "required_evidence_roles": ["supporting_fact", "rule"],
            },
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
            },
            {
                "id": "S2",
                "issue_ids": ["I2"],
                "text": "사업대상지 외부 사실 확인",
                "kind": "concept_relation",
                "source": "planner",
                "role": "supporting_fact",
            },
            {
                "id": "S3",
                "issue_ids": ["I2"],
                "text": "사업대상지 적용 기준",
                "kind": "concept_relation",
                "source": "planner",
                "role": "rule",
            },
        ],
    }


def _v1_payload() -> dict[str, object]:
    return {
        "format": QUESTION_PLAN_FORMAT,
        "version": 1,
        "original_question": QUESTION,
        "facts": [
            {"id": "F1", "text": "역 승강장 경계에서 300m 떨어져 있다.", "polarity": "positive"},
            {"id": "F2", "text": "부지 면적은 1,500㎡이다.", "polarity": "positive"},
        ],
        "assumptions": [],
        "issues": [
            {"id": "I1", "question": "역세권 거리 기준을 충족하는가?", "depends_on": []}
        ],
        "legal_anchors": [],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "역세권 승강장 경계 거리 기준",
                "kind": "concept_relation",
                "source": "planner",
            }
        ],
    }


def test_current_question_plan_contract_is_v2() -> None:
    assert QUESTION_PLAN_VERSION == 2


def test_v2_decodes_issue_required_roles_and_search_role() -> None:
    plan = decode_question_plan(_v2_payload(), QUESTION)

    assert plan.issues[0].required_evidence_roles == ("rule",)
    assert plan.issues[1].required_evidence_roles == ("supporting_fact", "rule")
    assert [request.role for request in plan.search_requests] == [
        "rule",
        "supporting_fact",
        "rule",
    ]


def test_question_plan_preserves_raw_question_and_separates_context_sources() -> None:
    payload = _v2_payload()
    payload["raw_user_question"] = "  " + QUESTION + "\n"
    payload["normalized_question"] = QUESTION
    payload["document_context"] = [
        {"text": "서울특별시 안심주택 운영기준", "source": "document"}
    ]
    payload["planner_inference"] = [
        {"text": "용도지역 변경 기준을 확인한다", "source": "planner"}
    ]

    plan = decode_question_plan(payload, QUESTION)
    document = question_plan_document(plan)

    assert plan.raw_user_question == "  " + QUESTION + "\n"
    assert plan.normalized_question == QUESTION
    assert plan.document_context[0].source == "document"
    assert plan.planner_inference[0].source == "planner"
    assert document["raw_user_question"] == "  " + QUESTION + "\n"
    assert document["document_context"] == payload["document_context"]


def test_question_plan_rejects_semantically_changed_raw_question() -> None:
    payload = _v2_payload()
    payload["raw_user_question"] = QUESTION.replace("300m", "500m")

    with pytest.raises(ValueError, match="raw_user_question does not match"):
        decode_question_plan(payload, QUESTION)


def test_v1_is_accepted_through_deterministic_legacy_adapter() -> None:
    plan = decode_question_plan(_v1_payload(), QUESTION)

    assert plan.issues[0].required_evidence_roles == ("rule",)
    assert plan.search_requests[0].role == "rule"
    assert question_plan_document(plan)["version"] == 2


def test_v2_rejects_empty_required_evidence_roles() -> None:
    payload = copy.deepcopy(_v2_payload())
    issues = payload["issues"]
    assert isinstance(issues, list)
    issues[0]["required_evidence_roles"] = []

    with pytest.raises(ValueError, match="required_evidence_roles must not be empty"):
        decode_question_plan(payload, QUESTION)


def test_v2_rejects_duplicate_required_evidence_roles() -> None:
    payload = copy.deepcopy(_v2_payload())
    issues = payload["issues"]
    assert isinstance(issues, list)
    issues[0]["required_evidence_roles"] = ["rule", "rule"]

    with pytest.raises(ValueError, match="required_evidence_roles contains duplicates"):
        decode_question_plan(payload, QUESTION)


def test_v2_rejects_search_role_not_required_by_linked_issue() -> None:
    payload = copy.deepcopy(_v2_payload())
    requests = payload["search_requests"]
    assert isinstance(requests, list)
    requests[0]["role"] = "supporting_fact"

    with pytest.raises(
        ValueError,
        match="search request S1 role supporting_fact is not required by issue I1",
    ):
        decode_question_plan(payload, QUESTION)


def test_v2_rejects_unknown_evidence_role() -> None:
    payload = copy.deepcopy(_v2_payload())
    requests = payload["search_requests"]
    assert isinstance(requests, list)
    requests[0]["role"] = "background"

    with pytest.raises(ValueError, match=r"unsupported search_requests\[0\]\.role"):
        decode_question_plan(payload, QUESTION)
