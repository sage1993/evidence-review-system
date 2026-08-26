from __future__ import annotations

import importlib
from decimal import Decimal
from typing import Any

import pytest

from evidence_review.contracts.common import BBox
from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit


def _facet_api() -> tuple[Any, Any]:
    try:
        module = importlib.import_module("evidence_review.retrieval.facets")
    except ModuleNotFoundError:
        pytest.fail("evidence_review.retrieval.facets is not implemented", pytrace=False)
    missing = [
        name
        for name in ("compile_required_facets", "evaluate_facet_coverage")
        if not hasattr(module, name)
    ]
    if missing:
        pytest.fail(f"facet coverage API missing: {missing}", pytrace=False)
    return module.compile_required_facets, module.evaluate_facet_coverage


def _plan():
    question = (
        "역 승강장 경계에서 300m 떨어진 부지가 역세권 거리 기준을 충족하거나 "
        "조건부 검토 대상이 되는가?"
    )
    return decode_question_plan(
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
                    "text": "역세권 승강장 경계 거리 기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                }
            ],
        },
        question,
    )


def _bundle(text: str) -> IssueRetrievalBundle:
    clause = ClauseRetrievalHit(
        clause_id="C-1",
        document_id="DOC-1",
        revision_id="REV-1",
        title="역세권 범위",
        text=text,
        channel_scores=(ChannelScore("clause_phrase", Decimal("1"), text),),
    )
    match = IssueCandidateMatch(
        search_request_id="S1",
        issue_id="I1",
        role="rule",
        query_text="역세권 승강장 경계 거리 기준",
        retrieval_query="역세권 승강장 경계 거리 기준",
        fallback_stage=FallbackStage.PHRASE,
    )
    hit = RetrievalHit(
        evidence_id="E-1",
        evidence_type="paragraph",
        document_id="DOC-1",
        revision_id="REV-1",
        page_number=1,
        bbox=BBox(10.0, 10.0, 100.0, 20.0),
        source_hash="a" * 64,
        title="역세권 범위",
        text=text,
        channel_scores=(ChannelScore("clause_citation", Decimal("1"), "C-1"),),
        final_score=Decimal("1"),
    )
    return IssueRetrievalBundle(
        candidates=(IssueClauseCandidate(clause=clause, matches=(match,), evidence=(hit,)),),
        selected_evidence=(hit,),
        budget_drops=(),
    )


def test_distance_clause_with_250_and_conditional_350_covers_both_facets() -> None:
    _, evaluate_facet_coverage = _facet_api()

    report = evaluate_facet_coverage(
        _plan(),
        _bundle(
            "역세권은 승강장 경계로부터 250m 이내를 원칙으로 하며 통합심의를 "
            "거치는 경우 350m 이내까지 검토할 수 있다."
        ),
    )

    issue = report.by_issue_id("I1")
    assert issue.covered_facet_ids == (
        "distance-normal-threshold",
        "distance-conditional-threshold",
    )
    assert issue.missing_facet_ids == ()


def test_generic_rule_does_not_resolve_missing_required_facets() -> None:
    _, evaluate_facet_coverage = _facet_api()
    plan = _plan()
    bundle = _bundle("역세권은 승강장 경계와의 거리 기준을 적용한다.")
    facet_report = evaluate_facet_coverage(plan, bundle)

    try:
        coverage = evaluate_issue_coverage(plan, bundle, facet_report=facet_report)
    except TypeError as error:
        pytest.fail(f"facet-aware issue coverage is not implemented: {error}", pytrace=False)

    issue = coverage.by_issue_id("I1")
    assert issue.status == "UNRESOLVED"
    assert "MISSING_REQUIRED_FACET" in issue.gap_codes
