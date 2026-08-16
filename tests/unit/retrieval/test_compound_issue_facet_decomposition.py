from __future__ import annotations

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.retrieval.facets import (
    augment_plan_with_facet_search_requests,
    compile_required_facets,
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
                {"id": "F1", "text": "대상 부지는 역 승강장 경계에서 300m 떨어져 있다.", "polarity": "positive"},
                {"id": "F2", "text": "대상 부지 면적은 1,500㎡이다.", "polarity": "positive"},
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


def _shared_numeric_sentence_plan():
    question = (
        "준공업지역에서 공공지원민간임대주택과 임대형기숙사를 복합한 안심주택을 "
        "계획하면서 공동주택 부분은 용적률 400% 완화를 적용하고 주차장 설치기준도 "
        "완화하려고 한다. 이 경우 400% 용적률 완화와 산업부지 확보비율, "
        "지구단위계획에 따른 추가 주차기준 완화는 각각 어떤 요건과 절차를 "
        "거쳐야 하는지 검토해줘."
    )
    issue_question = "준공업지역 공동주택 부분에 용적률 400% 기준을 적용할 수 있는가?"
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [
                {
                    "id": "F1",
                    "text": "계획안은 공동주택 부분에 용적률 400% 완화를 적용하려 한다.",
                    "polarity": "positive",
                }
            ],
            "assumptions": [],
            "issues": [
                {
                    "id": "I5",
                    "question": issue_question,
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S5",
                    "issue_ids": ["I5"],
                    "text": "준공업지역 공동주택 기본용적률",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                }
            ],
        },
        question,
    )


def test_compound_site_issue_requires_area_and_both_distance_facets() -> None:
    facets = compile_required_facets(_plan()).by_issue_id("I2")

    assert [item.facet_id for item in facets.required_facets] == [
        "minimum-area-threshold",
        "distance-normal-threshold",
        "distance-conditional-threshold",
    ]


def test_numeric_context_does_not_import_unrelated_facets_from_same_sentence() -> None:
    facets = compile_required_facets(_shared_numeric_sentence_plan()).by_issue_id("I5")

    assert [item.facet_id for item in facets.required_facets] == [
        "semi-industrial-far-threshold",
    ]


def test_compiler_adds_missing_minimum_area_query_to_compound_issue() -> None:
    compiled = augment_plan_with_facet_search_requests(_plan())

    i2_requests = [
        request
        for request in compiled.search_requests
        if "I2" in request.issue_ids
    ]
    assert [(item.id, item.text) for item in i2_requests] == [
        ("S2", "역세권 승강장 경계 거리 기준"),
        ("FACET-I2-minimum-area-threshold", "사업대상지 최소 면적"),
    ]


def test_compiler_does_not_duplicate_existing_minimum_area_query() -> None:
    compiled = augment_plan_with_facet_search_requests(_plan())

    i1_requests = [
        request
        for request in compiled.search_requests
        if "I1" in request.issue_ids
    ]
    assert [(item.id, item.text) for item in i1_requests] == [
        ("S1", "안심주택 사업대상지 최소 면적"),
    ]
