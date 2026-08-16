from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.contracts.question_plan import (
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.question_planning import issue_retrieval_bundle_document
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="주차기준 검토",
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="I1",
                question="주차기준은 무엇인가",
                depends_on=(),
                required_evidence_roles=("rule",),
            ),
        ),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                id="S1",
                issue_ids=("I1",),
                text="주차장 설치기준",
                kind="phrase",
                source="planner",
                role="rule",
            ),
        ),
    )


def _bundle() -> IssueRetrievalBundle:
    hit = RetrievalHit(
        evidence_id="E1",
        evidence_type="clause",
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
        title="제13조",
        text="주차장 설치기준",
        channel_scores=(ChannelScore("clause_citation", Decimal("1")),),
    )
    candidate = IssueClauseCandidate(
        clause=ClauseRetrievalHit(
            clause_id="CL1",
            document_id="DOC",
            revision_id="REV",
            title="제13조",
            text="주차장 설치기준",
            channel_scores=(ChannelScore("clause_phrase", Decimal("1")),),
        ),
        matches=(
            IssueCandidateMatch(
                search_request_id="S1",
                issue_id="I1",
                role="rule",
                query_text="주차장 설치기준",
                retrieval_query="주차장 설치기준",
                fallback_stage=FallbackStage.PHRASE,
            ),
        ),
        evidence=(hit,),
    )
    return IssueRetrievalBundle(
        candidates=(candidate,),
        selected_evidence=(hit,),
        budget_drops=(),
    )


def test_issue_retrieval_bundle_document_preserves_issue_role_and_fallback_lineage() -> None:
    document = issue_retrieval_bundle_document(
        _plan(),
        _bundle(),
        snapshot_hash="b" * 64,
    )

    assert document["query"]["primary"] == "주차기준 검토"
    hit = document["hits"][0]
    assert hit["issue_ids"] == ["I1"]
    assert hit["roles"] == ["rule"]
    assert hit["matches"] == [
        {
            "search_request_id": "S1",
            "issue_ids": ["I1"],
            "query_text": "주차장 설치기준",
            "retrieval_query": "주차장 설치기준",
            "origin": "llm",
            "role": "rule",
            "fallback_stage": "PHRASE",
        }
    ]
    assert hit["citation"]["citation_id"] == "CIT-E1"
