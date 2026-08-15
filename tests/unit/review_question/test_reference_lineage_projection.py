from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.retrieval.graph import ReferencePath, ReferenceStep
from evidence_review.retrieval.issue_bundle import IssueReferenceMatch, IssueRetrievalBundle
from evidence_review.retrieval.models import ChannelScore, RetrievalHit
from evidence_review.retrieval.reference_projection import apply_reference_lineage_to_bundle_document


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


def test_reference_projection_adds_issue_lineage_to_reference_evidence() -> None:
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
    retrieval = IssueRetrievalBundle(
        candidates=(),
        selected_evidence=(_hit("REF"),),
        budget_drops=(),
        reference_matches=(reference,),
    )
    document = {
        "hits": [
            {
                "evidence_id": "REF",
                "text": "참조 근거",
                "citation": {"citation_id": "CIT-REF"},
                "issue_ids": [],
                "roles": [],
                "matches": [],
            }
        ]
    }

    projected = apply_reference_lineage_to_bundle_document(document, retrieval)
    hit = projected["hits"][0]
    assert hit["issue_ids"] == ["I1"]
    assert hit["roles"] == ["rule"]
    assert hit["matches"][0]["fallback_stage"] == "REFERENCE_EXPANSION"
    assert hit["matches"][0]["search_request_id"] == "S1"
