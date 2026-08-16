from __future__ import annotations

from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.facets import evaluate_facet_coverage
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit
from evidence_review.rule_engine.fact_rule_comparison import evaluate_fact_rule_comparisons


def _plan():
    question = "일반 최소면적과 1,500㎡ 부지의 사업 가능 여부를 검토한다."
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [
                {"id": "F1", "text": "대상 부지 면적은 1,500㎡이다.", "polarity": "positive"},
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
                    "question": "1,500㎡ 부지가 일반 사업대상지 최소 면적 기준을 충족하는가?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                },
            ],
            "legal_anchors": [],
            "search_requests": [
                {"id": "S1", "issue_ids": ["I1"], "text": "사업대상지 최소 면적", "kind": "concept_relation", "source": "planner", "role": "rule"},
                {"id": "S2", "issue_ids": ["I2"], "text": "사업대상지 최소 면적", "kind": "concept_relation", "source": "planner", "role": "rule"},
            ],
        },
        question,
    )


def _bundle() -> IssueRetrievalBundle:
    text = "사업대상지의 최소 면적 기준은 1,000㎡로 한다."
    clause = ClauseRetrievalHit(
        clause_id="C-MIN",
        document_id="DOC-1",
        revision_id="REV-1",
        title="사업대상지 최소 면적",
        text=text,
        channel_scores=(ChannelScore("clause_phrase", Decimal("1"), text),),
    )
    matches = tuple(
        IssueCandidateMatch(
            search_request_id=f"S{index}",
            issue_id=f"I{index}",
            role="rule",
            query_text="사업대상지 최소 면적",
            retrieval_query="사업대상지 최소 면적",
            fallback_stage=FallbackStage.PHRASE,
        )
        for index in (1, 2)
    )
    hit = RetrievalHit(
        evidence_id="E-MIN",
        evidence_type="paragraph",
        document_id="DOC-1",
        revision_id="REV-1",
        page_number=1,
        bbox=BBox(0, 0, 100, 20),
        source_hash="a" * 64,
        title="사업대상지 최소 면적",
        text=text,
        channel_scores=(ChannelScore("clause_citation", Decimal("1"), "C-MIN"),),
        final_score=Decimal("1"),
    )
    return IssueRetrievalBundle(
        candidates=(IssueClauseCandidate(clause=clause, matches=matches, evidence=(hit,)),),
        selected_evidence=(hit,),
        budget_drops=(),
    )


def test_global_area_fact_is_compared_only_for_issue_that_preserves_1500_value() -> None:
    plan = _plan()
    bundle = _bundle()
    facets = evaluate_facet_coverage(plan, bundle)

    comparisons = evaluate_fact_rule_comparisons(plan, bundle, facets)

    assert [(item.issue_id, item.facet_id) for item in comparisons] == [
        ("I2", "minimum-area-threshold"),
    ]
    assert comparisons[0].fact_value == "1500"
    assert comparisons[0].threshold_value == "1000"
    assert comparisons[0].satisfied is True
