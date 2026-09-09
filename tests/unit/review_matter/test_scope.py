from __future__ import annotations

import copy
import importlib
import json

import pytest

from evidence_review.contracts.question_plan import QUESTION_PLAN_FORMAT

QUESTION = "제12조 기준에서 300m 이격과 1,500㎡ 부지의 검토 가능 여부를 확인해줘."


def _scope_module():
    try:
        return importlib.import_module("evidence_review.review_matter.scope")
    except ModuleNotFoundError as error:
        pytest.fail(f"REVIEW_SCOPE_PACKAGE_MISSING: {error}")


def _question_plan_payload() -> dict[str, object]:
    return {
        "format": QUESTION_PLAN_FORMAT,
        "version": 2,
        "original_question": QUESTION,
        "facts": [
            {"id": "F1", "text": "경계에서 300m 이격되어 있다.", "polarity": "positive"},
            {"id": "F2", "text": "부지 면적은 1,500㎡이다.", "polarity": "positive"},
        ],
        "assumptions": [
            {"id": "A1", "text": "현장 측정값은 재확인이 필요할 수 있다.", "polarity": "negative"}
        ],
        "issues": [
            {
                "id": "I1",
                "question": "300m 이격 기준을 충족하는가?",
                "depends_on": [],
                "required_evidence_roles": ["rule"],
            },
            {
                "id": "I2",
                "question": "부지 사실을 확인할 수 있는가?",
                "depends_on": ["I1"],
                "required_evidence_roles": ["supporting_fact", "rule"],
            },
        ],
        "legal_anchors": [{"text": "제12조", "source": "user"}],
        "search_requests": [
            {
                "id": "S1",
                "issue_ids": ["I1"],
                "text": "300m 이격 법정 기준",
                "kind": "concept_relation",
                "source": "planner",
                "role": "rule",
            },
            {
                "id": "S2",
                "issue_ids": ["I2"],
                "text": "부지 외부 사실 확인",
                "kind": "concept_relation",
                "source": "planner",
                "role": "supporting_fact",
            },
            {
                "id": "S3",
                "issue_ids": ["I2"],
                "text": "제12조 적용 기준",
                "kind": "legal_anchor",
                "source": "planner",
                "role": "rule",
            },
        ],
    }


def _scope_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/review-scope",
        "version": 1,
        "question": QUESTION,
        "facts": copy.deepcopy(_question_plan_payload()["facts"]),
        "assumptions": copy.deepcopy(_question_plan_payload()["assumptions"]),
        "issues": copy.deepcopy(_question_plan_payload()["issues"]),
        "legal_anchors": copy.deepcopy(_question_plan_payload()["legal_anchors"]),
        "search_requests": copy.deepcopy(_question_plan_payload()["search_requests"]),
        "origin": "PLANNER",
        "question_plan_sha256": "a" * 64,
    }


def test_review_scope_decodes_and_preserves_question_plan_semantics() -> None:
    scope_module = _scope_module()

    scope = scope_module.decode_review_scope(_scope_payload())

    assert scope.question == QUESTION
    assert scope.origin == "PLANNER"
    assert scope.question_plan_sha256 == "a" * 64
    assert scope.facts[0].text.endswith("300m 이격되어 있다.")
    assert scope.facts[1].text.endswith("1,500㎡이다.")
    assert scope.assumptions[0].polarity == "negative"
    assert scope.issues[1].depends_on == ("I1",)
    assert scope.legal_anchors[0].source == "user"
    assert scope.search_requests[2].issue_ids == ("I2",)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload.pop("origin"),
        lambda payload: payload["issues"].append(copy.deepcopy(payload["issues"][0])),
        lambda payload: payload.update({"status": "READY_FOR_HUMAN_REVIEW"}),
        lambda payload: payload.update({"evidence": [{"evidence_id": "E1"}]}),
    ],
)
def test_review_scope_rejects_unknown_missing_duplicate_and_authority_fields(mutation) -> None:
    payload = _scope_payload()
    mutation(payload)

    with pytest.raises(ValueError):
        _scope_module().decode_review_scope(payload)


def test_review_scope_rejects_empty_issue_set() -> None:
    payload = _scope_payload()
    payload["issues"] = []

    with pytest.raises(ValueError, match="issues"):
        _scope_module().decode_review_scope(payload)


@pytest.mark.parametrize(
    ("dependencies", "cycle"),
    [(["UNKNOWN"], False), (["I2"], False), (["I1"], True)],
)
def test_review_scope_rejects_unknown_self_and_cyclic_dependencies(dependencies, cycle) -> None:
    payload = _scope_payload()
    issues = payload["issues"]
    assert isinstance(issues, list)
    issues[1]["depends_on"] = dependencies
    if cycle:
        issues[0]["depends_on"] = ["I2"]

    with pytest.raises(ValueError, match="depend"):
        _scope_module().decode_review_scope(payload)


def test_review_scope_rejects_search_request_bound_to_wrong_issue_role() -> None:
    payload = _scope_payload()
    requests = payload["search_requests"]
    assert isinstance(requests, list)
    requests[0]["role"] = "supporting_fact"

    with pytest.raises(ValueError, match="role|issue"):
        _scope_module().decode_review_scope(payload)


def test_review_scope_round_trip_is_deterministic() -> None:
    scope_module = _scope_module()
    scope = scope_module.decode_review_scope(_scope_payload())

    first_document = scope_module.review_scope_document(scope)
    second_document = scope_module.review_scope_document(
        scope_module.decode_review_scope(first_document)
    )

    assert first_document == second_document
    assert json.dumps(
        first_document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) == json.dumps(second_document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_review_scope_is_not_evidence_or_formal_status() -> None:
    scope_module = _scope_module()
    scope = scope_module.decode_review_scope(_scope_payload())

    assert not hasattr(scope, "evidence")
    assert not hasattr(scope, "final_status")
    assert scope_module.review_scope_document(scope)["format"] == "evidence-review/review-scope"
