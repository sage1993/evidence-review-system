from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.graph import ReferencePath, ReferenceStep
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueReferenceMatch,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit


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


def test_issue_retrieval_bundle_can_bind_reference_hit_to_originating_issue_query() -> None:
    seed = _hit("SEED")
    referenced = _hit("REF")
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
            text="주차기준은 별표를 따른다",
            channel_scores=(ChannelScore("test", Decimal("1")),),
        ),
        matches=(match,),
        evidence=(seed,),
    )
    reference = IssueReferenceMatch(
        evidence_id="REF",
        issue_id="I1",
        search_request_id="S1",
        role="rule",
        query_text="주차기준",
        retrieval_query="주차장 설치기준",
        source_evidence_id="SEED",
        path=ReferencePath(
            target_id="REF",
            steps=(
                ReferenceStep(
                    source_id="SEED",
                    target_id="REF",
                    relation_type="cited_clause",
                    depth=1,
                ),
            ),
        ),
    )

    bundle = IssueRetrievalBundle(
        candidates=(candidate,),
        selected_evidence=(seed, referenced),
        budget_drops=(),
        reference_matches=(reference,),
    )

    assert bundle.reference_matches[0].issue_id == "I1"
    assert bundle.reference_matches[0].path.target_id == "REF"
