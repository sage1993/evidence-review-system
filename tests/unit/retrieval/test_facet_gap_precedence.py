from __future__ import annotations

import importlib
from typing import Any

import pytest

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle


def _evaluate_facet_coverage() -> Any:
    try:
        module = importlib.import_module("evidence_review.retrieval.facets")
    except ModuleNotFoundError:
        pytest.fail("evidence_review.retrieval.facets is not implemented", pytrace=False)
    if not hasattr(module, "evaluate_facet_coverage"):
        pytest.fail("evaluate_facet_coverage is not implemented", pytrace=False)
    return module.evaluate_facet_coverage


def test_zero_candidate_issue_remains_retrieval_miss_even_when_facets_are_required() -> None:
    question = "안심주택의 일반 사업대상지 최소 면적은 얼마인가?"
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
                    "question": question,
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
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
                }
            ],
        },
        question,
    )
    bundle = IssueRetrievalBundle(candidates=(), selected_evidence=(), budget_drops=())
    facets = _evaluate_facet_coverage()(plan, bundle)

    try:
        support = evaluate_issue_coverage(plan, bundle, facet_report=facets).by_issue_id("I1")
    except TypeError as error:
        pytest.fail(f"facet-aware issue coverage is not implemented: {error}", pytrace=False)

    assert support.status == "UNRESOLVED"
    assert support.gap_codes == ("RETRIEVAL_MISS",)
