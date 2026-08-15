from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.contracts.question_plan import QuestionIssue, QuestionPlan
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.coverage import CoverageReport, IssueSupport
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.graph import ReferencePath, ReferenceStep
from evidence_review.retrieval.issue_bundle import (
    BudgetDrop,
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueFallbackTrace,
    IssueReferenceMatch,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit
from evidence_review.retrieval.trace import retrieval_trace_document


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="복합 검토",
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="I1",
                question="주차기준 검토",
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(),
    )


def _hit(evidence_id: str) -> RetrievalHit:
    return RetrievalHit(
        evidence_id=evidence_id,
        evidence_type="clause",
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
        title=evidence_id,
        text=evidence_id,
        channel_scores=(ChannelScore("test", Decimal("1")),),
    )


def test_retrieval_trace_reconstructs_candidate_reference_coverage_and_citations() -> None:
    seed = _hit("E1")
    referenced = _hit("E2")
    match = IssueCandidateMatch(
        search_request_id="S1",
        issue_id="I1",
        role="rule",
        query_text="주차기준",
        retrieval_query="주차장 설치기준",
        fallback_stage=FallbackStage.APPROVED_ALIAS,
    )
    candidate = IssueClauseCandidate(
        clause=ClauseRetrievalHit(
            clause_id="CL1",
            document_id="DOC",
            revision_id="REV",
            title="제13조",
            text="주차장 설치기준",
            channel_scores=(ChannelScore("clause", Decimal("0.8")),),
        ),
        matches=(match,),
        evidence=(seed,),
    )
    reference = IssueReferenceMatch(
        evidence_id="E2",
        issue_id="I1",
        search_request_id="S1",
        role="rule",
        query_text="주차기준",
        retrieval_query="주차장 설치기준",
        source_evidence_id="E1",
        path=ReferencePath(
            target_id="E2",
            steps=(
                ReferenceStep(
                    source_id="E1",
                    target_id="E2",
                    relation_type="cited_clause",
                    depth=1,
                ),
            ),
        ),
    )
    bundle = IssueRetrievalBundle(
        candidates=(candidate,),
        selected_evidence=(seed, referenced),
        budget_drops=(
            BudgetDrop(
                issue_id="I1",
                search_request_id="S2",
                reason="QUERY_BUDGET",
            ),
        ),
        fallback_traces=(
            IssueFallbackTrace(
                issue_id="I1",
                search_request_id="S1",
                role="rule",
                stage=FallbackStage.APPROVED_ALIAS,
                input_query="주차기준",
                derived_query="주차장 설치기준",
                hit_count=1,
            ),
        ),
        reference_matches=(reference,),
    )
    coverage = CoverageReport(
        issues=(
            IssueSupport(
                issue_id="I1",
                status="RESOLVED",
                evidence_ids=("E1",),
                covered_roles=("rule",),
                missing_roles=(),
                gap_codes=(),
            ),
        )
    )

    trace = retrieval_trace_document(_plan(), bundle, coverage)
    issue = trace["issues"][0]
    assert issue["coverage"]["status"] == "RESOLVED"
    assert issue["candidates"][0]["clause_id"] == "CL1"
    assert issue["candidates"][0]["raw_score"] == "0.8"
    assert issue["references"][0]["path"][0]["target_id"] == "E2"
    assert issue["budget_drops"][0]["reason"] == "QUERY_BUDGET"
    assert trace["selected_evidence"][1]["citation_id"] == "CIT-E2"
