from __future__ import annotations

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.facets import evaluate_facet_coverage
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle


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
            "search_requests": [],
        },
        question,
    )
    bundle = IssueRetrievalBundle(candidates=(), selected_evidence=(), budget_drops=())
    facets = evaluate_facet_coverage(plan, bundle)

    support = evaluate_issue_coverage(plan, bundle, facet_report=facets).by_issue_id("I1")

    assert support.status == "UNRESOLVED"
    assert support.gap_codes == ("RETRIEVAL_MISS",)
