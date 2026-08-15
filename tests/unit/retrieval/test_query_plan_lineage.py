from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.retrieval.fusion import fuse_hits, fusion_document
from evidence_review.retrieval.models import ChannelScore, RetrievalHit, RetrievalMatch


def _hit(*, channel: str, match: RetrievalMatch) -> RetrievalHit:
    return RetrievalHit(
        evidence_id="E1",
        evidence_type="text",
        document_id="D1",
        revision_id="R1",
        page_number=1,
        bbox=BBox(0.0, 0.0, 1.0, 1.0),
        source_hash="a" * 64,
        title="title",
        text="evidence",
        channel_scores=(ChannelScore(channel, Decimal("1"), "trace"),),
        matches=(match,),
    )


def test_with_match_merges_issue_ids_deterministically() -> None:
    base = _hit(
        channel="fts_phrase",
        match=RetrievalMatch("S1", ("I2",), "설치 기준", "llm"),
    )

    merged = base.with_match(RetrievalMatch("S1", ("I1",), "설치 기준", "llm"))

    assert merged.matches == (RetrievalMatch("S1", ("I1", "I2"), "설치 기준", "llm"),)


def test_fusion_merges_matches_without_changing_score() -> None:
    left = _hit(
        channel="fts_phrase",
        match=RetrievalMatch("S1", ("I1",), "설치 기준", "llm"),
    )
    right = _hit(
        channel="fts_token_and",
        match=RetrievalMatch("S2", ("I2",), "실외기 설치", "llm"),
    )

    fused = fuse_hits(((left,), (right,)))

    assert fused[0].final_score == Decimal("0.70")
    assert [match.search_request_id for match in fused[0].matches] == ["S1", "S2"]


def test_fusion_document_exports_issue_search_evidence_matches() -> None:
    hit = _hit(
        channel="fts_phrase",
        match=RetrievalMatch("S1", ("I1",), "설치 기준", "user"),
    )

    document = fusion_document((hit,))

    assert document["hits"][0]["matches"] == [
        {
            "search_request_id": "S1",
            "issue_ids": ["I1"],
            "query_text": "설치 기준",
            "origin": "user",
        }
    ]
