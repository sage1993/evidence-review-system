from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    _merge_candidate,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit


def _candidate(search_request_id: str, query: str) -> IssueClauseCandidate:
    channel = ChannelScore("fts_token_prefix_and", Decimal("1"), query)
    hit = RetrievalHit(
        evidence_id="E1",
        evidence_type="clause",
        document_id="DOC1",
        revision_id="REV1",
        page_number=1,
        bbox=BBox(0, 0, 10, 10),
        source_hash="a" * 64,
        title="주차장 조례",
        text="주차장은 별표 2에 따른다.",
        channel_scores=(channel,),
    )
    return IssueClauseCandidate(
        clause=ClauseRetrievalHit(
            clause_id="E1",
            document_id="DOC1",
            revision_id="REV1",
            title="주차장 조례",
            text=hit.text,
            channel_scores=(channel,),
        ),
        matches=(
            IssueCandidateMatch(
                search_request_id=search_request_id,
                issue_id="I1",
                role="rule",
                query_text=query,
                retrieval_query=query,
                fallback_stage=FallbackStage.LEGACY_ELEMENT,
            ),
        ),
        evidence=(hit,),
    )


def test_duplicate_legacy_candidates_preserve_evidence_and_both_query_matches() -> None:
    merged = _merge_candidate(
        _candidate("S1", "주차장"),
        _candidate("USER-EXP-01", "별표 2"),
    )

    assert [item.evidence_id for item in merged.evidence] == ["E1"]
    assert {item.search_request_id for item in merged.matches} == {"S1", "USER-EXP-01"}
    detail = merged.evidence[0].channel_scores[0].detail
    assert {part.strip() for part in detail.split("|")} == {"주차장", "별표 2"}
