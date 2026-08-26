from __future__ import annotations

import importlib
from typing import Any

import pytest

from evidence_review.contracts.question_plan import decode_question_plan


def _facet_api() -> tuple[Any, Any, Any]:
    try:
        module = importlib.import_module("evidence_review.retrieval.facets")
    except ModuleNotFoundError:
        pytest.fail("evidence_review.retrieval.facets is not implemented", pytrace=False)
    missing = [
        name
        for name in (
            "compile_required_facets",
            "augment_plan_with_facet_search_requests",
            "issue_context_text",
        )
        if not hasattr(module, name)
    ]
    if missing:
        pytest.fail(f"facet compiler API missing: {missing}", pytrace=False)
    return (
        module.compile_required_facets,
        module.augment_plan_with_facet_search_requests,
        module.issue_context_text,
    )


def _plan():
    question = (
        "안심주택의 일반 최소면적은 얼마인가? "
        "역 승강장 경계에서 300m 떨어진 1,500㎡ 부지에서 사업을 추진할 수 있는가?"
    )
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [
                {
                    "id": "F1",
                    "text": "대상 부지는 역 승강장 경계에서 300m 떨어져 있다.",
                    "polarity": "positive",
                },
                {
                    "id": "F2",
                    "text": "대상 부지 면적은 1,500㎡이다.",
                    "polarity": "positive",
                },
            ],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "안심주택의 일반 사업대상지 최소 면적 기준은 무엇인가?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                },
                {
                    "id": "I2",
                    "question": (
                        "역 승강장 경계에서 300m 떨어진 부지가 역세권 거리 기준을 "
                        "충족하거나 조건부 검토 대상이 되는가?"
                    ),
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                },
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "안심주택 사업대상지 최소 면적",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
                {
                    "id": "S2",
                    "issue_ids": ["I2"],
                    "text": "역세권 승강장 경계 거리 기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
            ],
        },
        question,
    )


def test_compound_site_issue_requires_area_and_both_distance_facets() -> None:
    compile_required_facets, _, _ = _facet_api()

    facets = compile_required_facets(_plan()).by_issue_id("I2")

    assert [item.facet_id for item in facets.required_facets] == [
        "minimum-area-threshold",
        "distance-normal-threshold",
        "distance-conditional-threshold",
    ]


def test_issue_context_recovers_only_same_sentence_area_fact() -> None:
    _, _, issue_context_text = _facet_api()
    plan = _plan()
    issue = plan.issues[1]

    context = issue_context_text(plan, issue.question)

    assert "300m" in context
    assert "1,500㎡" in context
    assert "일반 최소면적은 얼마인가" not in context


def test_compiler_adds_only_missing_minimum_area_query() -> None:
    _, augment, _ = _facet_api()

    compiled = augment(_plan())
    i2_requests = [request for request in compiled.search_requests if "I2" in request.issue_ids]

    assert [(item.id, item.text) for item in i2_requests] == [
        ("S2", "역세권 승강장 경계 거리 기준"),
        ("FACET-I2-minimum-area-threshold", "사업대상지 최소 면적"),
    ]
