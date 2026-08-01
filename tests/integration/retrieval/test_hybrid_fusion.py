from decimal import Decimal

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.common import BBox
from ansim_review.retrieval.fusion import fusion_document, fuse_hits
from ansim_review.retrieval.models import ChannelScore, RetrievalHit


def _hit(
    evidence_id: str,
    document_id: str = "LAW1",
    channel: str = "structured_exact",
) -> RetrievalHit:
    return RetrievalHit(
        evidence_id=evidence_id,
        evidence_type="clause",
        document_id=document_id,
        revision_id=f"{document_id}-REV1",
        page_number=1,
        bbox=BBox(0, 0, 10, 10),
        source_hash=("a" if document_id == "LAW1" else "b") * 64,
        title="기준",
        text="기준 내용",
        channel_scores=(ChannelScore(channel, Decimal("1"), "test"),),
    )


def test_equal_scores_sort_by_stable_evidence_id() -> None:
    fused = fuse_hits(((_hit("E2"), _hit("E1")),))
    assert [hit.evidence_id for hit in fused] == ["E1", "E2"]
    assert fused[0].final_score == Decimal("1.00")


def test_fusion_preserves_channels_and_is_byte_reproducible() -> None:
    e1_structured = _hit("E1")
    e1_fts = _hit("E1", channel="fts")
    e2 = _hit("E2")
    unrelated = _hit(
        "A0",
        document_id="LAW2",
        channel="linked_visual_table",
    )

    first = fuse_hits(((e2, e1_structured), (e1_fts,), (unrelated,)))
    second = fuse_hits(
        ((unrelated,), (e1_fts,), (e1_structured, e2))
    )

    assert [
        hit.evidence_id for hit in first if hit.document_id == "LAW1"
    ] == ["E1", "E2"]
    assert [item.channel for item in first[0].channel_scores] == [
        "fts",
        "structured_exact",
    ]
    assert dump_bytes(fusion_document(first)) == dump_bytes(
        fusion_document(second)
    )
