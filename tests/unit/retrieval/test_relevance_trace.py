from __future__ import annotations

import importlib

import pytest

from evidence_review.contracts.question_plan import QuestionIssue, QuestionPlan
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle
from evidence_review.retrieval.trace import retrieval_trace_document


def test_retrieval_trace_preserves_rejected_clause_reason_codes() -> None:
    issue_bundle_module = importlib.import_module("evidence_review.retrieval.issue_bundle")
    missing = [
        name
        for name in ("IssueFallbackTrace", "IssueRelevanceDecision")
        if not hasattr(issue_bundle_module, name)
    ]
    if missing:
        pytest.fail(f"relevance trace API missing: {missing}", pytrace=False)

    IssueFallbackTrace = issue_bundle_module.IssueFallbackTrace
    IssueRelevanceDecision = issue_bundle_module.IssueRelevanceDecision

    plan = QuestionPlan(
        original_question="역세권 용도지역 변경 기준은?",
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="I1",
                question="역세권 용도지역 변경 기준은?",
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(),
    )
    decision = IssueRelevanceDecision(
        issue_id="I1",
        search_request_id="S1",
        clause_id="C-ARTERIAL",
        accepted=False,
        reason_codes=("REJECT_SUBJECT_CONFLICT",),
    )
    try:
        fallback_trace = IssueFallbackTrace(
            issue_id="I1",
            search_request_id="S1",
            role="rule",
            stage=FallbackStage.PHRASE,
            input_query="역세권 용도지역 변경 기준",
            derived_query="역세권 용도지역 변경 기준",
            hit_count=0,
            relevance_decisions=(decision,),
        )
    except TypeError as error:
        pytest.fail(f"IssueFallbackTrace relevance_decisions missing: {error}", pytrace=False)

    bundle = IssueRetrievalBundle(
        candidates=(),
        selected_evidence=(),
        budget_drops=(),
        fallback_traces=(fallback_trace,),
    )
    coverage = evaluate_issue_coverage(plan, bundle)

    trace = retrieval_trace_document(plan, bundle, coverage)
    issue = trace["issues"][0]
    assert issue["relevance_decisions"] == [
        {
            "search_request_id": "S1",
            "stage": "PHRASE",
            "clause_id": "C-ARTERIAL",
            "accepted": False,
            "reason_codes": ["REJECT_SUBJECT_CONFLICT"],
        }
    ]
    assert issue["fallback_attempts"][0]["relevance_decisions"] == [
        {
            "clause_id": "C-ARTERIAL",
            "accepted": False,
            "reason_codes": ["REJECT_SUBJECT_CONFLICT"],
        }
    ]
