from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.retrieval.bundle import _trace_hits
from evidence_review.retrieval.models import ChannelScore, RetrievalHit, RetrievalMatch


def test_trace_hits_attaches_search_request_and_issue_lineage() -> None:
    source = RetrievalHit(
        evidence_id="E1",
        evidence_type="text",
        document_id="D1",
        revision_id="R1",
        page_number=1,
        bbox=BBox(0.0, 0.0, 1.0, 1.0),
        source_hash="a" * 64,
        title="title",
        text="evidence",
        channel_scores=(ChannelScore("fts_phrase", Decimal("1"), "raw"),),
    )

    traced = _trace_hits(
        (source,),
        origin="llm",
        term="에어컨 설치기준",
        search_request_ids=("S1",),
        issue_ids=("I1",),
    )

    assert traced[0].channel_scores[0].detail == "llm:에어컨 설치기준"
    assert traced[0].matches == (
        RetrievalMatch("S1", ("I1",), "에어컨 설치기준", "llm"),
    )
